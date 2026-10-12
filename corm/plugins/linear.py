"""
Linear (https://linear.app) source plugin.

Authenticates with a Linear personal API key (or an OAuth access token).
Each Linear Team is a Channel. Issues and their comments are imported as
Conversations (comments threaded under their issue), and completed issues are
recorded as "Completed Issue" Contributions by the assignee.
"""
import datetime
from time import sleep

import requests
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, reverse
from django.urls import path

from corm.plugins import BasePlugin, PluginImporter
from corm.models import Source, Contribution, ContributionType
from frontendv2.views import SavannahView

LINEAR_GRAPHQL_URL = 'https://api.linear.app/graphql'
LINEAR_TIMESTAMP = '%Y-%m-%dT%H:%M:%S.%fZ'
LINEAR_PAGE_SIZE = 50
LINEAR_COMMENT_PAGE_SIZE = 100

USER_FIELDS = 'id name displayName email avatarUrl url'

VIEWER_QUERY = '''
query {
  viewer { %s organization { id name urlKey } }
}
''' % USER_FIELDS

TEAMS_QUERY = '''
query Teams($after: String) {
  teams(first: 50, after: $after) {
    nodes { id key name description private }
    pageInfo { hasNextPage endCursor }
  }
}
'''

ISSUES_QUERY = '''
query Issues($teamId: ID!, $since: DateTimeOrDuration!, $after: String) {
  issues(
    filter: { team: { id: { eq: $teamId } }, updatedAt: { gte: $since } }
    orderBy: updatedAt
    includeArchived: true
    first: %(page_size)s
    after: $after
  ) {
    nodes {
      id identifier title description url createdAt updatedAt completedAt
      creator { %(user)s }
      assignee { %(user)s }
      comments(first: %(comment_page_size)s) {
        nodes { id body url createdAt user { %(user)s } }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
''' % {'user': USER_FIELDS, 'page_size': LINEAR_PAGE_SIZE, 'comment_page_size': LINEAR_COMMENT_PAGE_SIZE}

USER_QUERY = '''
query User($id: String!) {
  user(id: $id) { %s }
}
''' % USER_FIELDS


class LinearAPIError(Exception):
    pass


def auth_header(token):
    """Personal API keys are sent bare; OAuth access tokens need a Bearer prefix."""
    if token.startswith('lin_api_'):
        return token
    return 'Bearer %s' % token


def graphql(token, query, variables=None, retries=None, timeout=30):
    """POST a GraphQL query to Linear, backing off on rate limits.

    Returns the ``data`` dict or raises LinearAPIError.
    """
    if retries is None:
        retries = getattr(settings, 'API_BACKOFF_ATTEMPTS', 5)
    backoff_seconds = getattr(settings, 'API_BACKOFF_SECONDS', 10)
    headers = {
        'Authorization': auth_header(token),
        'Content-Type': 'application/json',
    }
    payload = {'query': query, 'variables': variables or {}}
    if settings.DEBUG:
        print("API Call: %s %s" % (LINEAR_GRAPHQL_URL, (query.strip().splitlines() or [''])[0]))
    resp = requests.post(LINEAR_GRAPHQL_URL, json=payload, headers=headers, timeout=timeout)
    backoff_time = 0
    while resp.status_code == 429 and retries > 0:
        retries -= 1
        backoff_time += backoff_seconds
        if settings.DEBUG:
            print("API backoff, %s retries remaining" % retries)
        sleep(backoff_time)
        resp = requests.post(LINEAR_GRAPHQL_URL, json=payload, headers=headers, timeout=timeout)

    if resp.status_code == 401 or resp.status_code == 403:
        raise LinearAPIError("Linear rejected the API key (HTTP %s)" % resp.status_code)
    if resp.status_code != 200:
        raise LinearAPIError("Linear API returned HTTP %s: %s" % (resp.status_code, resp.text[:200]))
    body = resp.json()
    if body.get('errors'):
        raise LinearAPIError("; ".join(err.get('message', 'Unknown error') for err in body['errors']))
    return body.get('data', {})


class LinearForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['name', 'auth_secret']
        labels = {
            'name': 'Source name',
            'auth_secret': 'Linear API key',
        }
        help_texts = {
            'name': 'Optional. Defaults to your Linear workspace name.',
            'auth_secret': 'A personal API key from Linear > Settings > API, or an OAuth access token.',
        }
        widgets = {
            'auth_secret': forms.PasswordInput(render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super(LinearForm, self).__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.fields['auth_secret'].required = True


class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    @login_required
    def as_view(request):
        view = SourceAdd(request, community_id=request.session['community'])
        if not view.community.management.can_add_source():
            messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
            return redirect('sources', community_id=view.community.id)
        new_source = Source(community=view.community, connector="corm.plugins.linear", server="https://linear.app", icon_name="fas fa-tasks")
        if request.method == "POST":
            form = LinearForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                try:
                    data = graphql(source.auth_secret, VIEWER_QUERY, retries=0, timeout=10)
                    org = data['viewer']['organization']
                    source.auth_id = org['urlKey']
                    source.server = 'https://linear.app/%s' % org['urlKey']
                    if not source.name:
                        source.name = org['name']
                    source.save()
                    messages.success(request, 'Your Linear workspace has been connected! Pick which teams you want to track from the list below.')
                    return redirect('channels', community_id=view.community.id, source_id=source.id)
                except (LinearAPIError, KeyError, requests.RequestException) as e:
                    form.add_error('auth_secret', 'Unable to connect to Linear with this API key: %s' % e)

        else:
            form = LinearForm(instance=new_source)
        context = view.context
        context.update({
            'source_form': form,
            'source_plugin': 'Linear',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, 'savannahv2/source_add.html', context)


urlpatterns = [
    path('auth', SourceAdd.as_view, name='linear_auth'),
]


class LinearPlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_identity_url(self, contact):
        if contact.source.server and contact.detail:
            return "%s/profiles/%s" % (contact.source.server, contact.detail)
        return None

    def get_icon_name(self):
        return 'fas fa-tasks'

    def get_auth_url(self):
        return reverse('linear_auth')

    def get_source_type_name(self):
        return "Linear"

    def get_import_command_name(self):
        return "linear"

    def get_source_importer(self, source):
        return LinearImporter(source)

    def get_channels(self, source):
        channels = []
        after = None
        while True:
            data = graphql(source.auth_secret, TEAMS_QUERY, {'after': after}, retries=0, timeout=10)
            teams = data.get('teams', {})
            for team in teams.get('nodes', []):
                channels.append({
                    'id': team['id'],
                    'name': '%s (%s)' % (team['name'], team['key']),
                    'topic': team.get('description') or '',
                    'count': '',
                    'is_private': team.get('private', False),
                    'is_archived': False,
                })
            page = teams.get('pageInfo', {})
            if page.get('hasNextPage') and page.get('endCursor'):
                after = page['endCursor']
            else:
                break
        return channels


class LinearImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = LINEAR_TIMESTAMP
        self.COMPLETED_CONTRIBUTION, created = ContributionType.objects.get_or_create(
            community=source.community,
            source=source,
            name="Completed Issue",
        )

    def query(self, query, variables=None):
        if self.verbosity:
            print("API Call: %s %s" % (LINEAR_GRAPHQL_URL, (query.strip().splitlines() or [''])[0]))
        return graphql(self.source.auth_secret, query, variables)

    def strptime(self, dtimestamp):
        # Linear timestamps carry milliseconds; tolerate ones that don't.
        try:
            return super().strptime(dtimestamp)
        except ValueError:
            return datetime.datetime.strptime(dtimestamp, '%Y-%m-%dT%H:%M:%SZ')

    def update_source(self):
        if not self.source.auth_id or self.source.server in (None, '', 'https://linear.app'):
            data = self.query(VIEWER_QUERY)
            org = data.get('viewer', {}).get('organization')
            if org:
                self.source.auth_id = org['urlKey']
                self.source.server = 'https://linear.app/%s' % org['urlKey']
                self.source.save()

    def make_linear_member(self, user, channel, tstamp, speaker=False):
        """Create or fetch the Member for a Linear user object, or None for bot/system actors."""
        if not user or not user.get('id'):
            return None
        origin_id = 'linear.app/%s' % user['id']
        return self.make_member(
            origin_id,
            detail=user.get('displayName') or user.get('name'),
            tstamp=tstamp,
            channel=channel,
            email_address=user.get('email'),
            avatar_url=user.get('avatarUrl'),
            name=user.get('name') or user.get('displayName'),
            speaker=speaker,
        )

    def update_identity(self, identity):
        # Issue and comment payloads already carry name, email and avatar, so
        # only spend an API call when the contact is missing that data.
        if identity.name and (identity.email_address or identity.avatar_url):
            return
        user_id = identity.origin_id.split('/', 1)[-1]
        try:
            data = self.query(USER_QUERY, {'id': user_id})
        except LinearAPIError as e:
            print("Failed to lookup identity info: %s" % e)
            return
        user = data.get('user')
        if not user:
            return
        identity.name = user.get('name')
        identity.detail = user.get('displayName') or identity.detail
        identity.email_address = user.get('email')
        identity.avatar_url = user.get('avatarUrl')
        identity.save()

        if identity.member.name == identity.detail and identity.name:
            identity.member.name = identity.name
        if identity.member.email_address is None:
            identity.member.email_address = identity.email_address
        identity.member.save()

    def import_channel(self, channel, from_date, full_import=False):
        team_id = channel.origin_id
        since = from_date.strftime(LINEAR_TIMESTAMP)
        after = None
        while True:
            data = self.query(ISSUES_QUERY, {'teamId': team_id, 'since': since, 'after': after})
            issues = data.get('issues', {})
            for issue in issues.get('nodes', []):
                self.import_issue(channel, issue)
            page = issues.get('pageInfo', {})
            if page.get('hasNextPage') and page.get('endCursor'):
                after = page['endCursor']
            else:
                break

    def import_issue(self, channel, issue):
        community = self.source.community
        tstamp = self.strptime(issue['createdAt'])
        participants = set()
        conversations = set()

        creator = self.make_linear_member(issue.get('creator'), channel, tstamp, speaker=True)
        if creator is None:
            # Issues created by integrations have no creator; nothing to attribute.
            return
        participants.add(creator)

        content = issue.get('title') or ''
        if issue.get('description'):
            content = '%s\n\n%s' % (content, issue['description'])
        content = content.replace("\x00", "�")

        convo = self.make_conversation(
            origin_id=issue['id'],
            channel=channel,
            speaker=creator,
            content=content,
            tstamp=tstamp,
            location=issue.get('url'),
        )
        conversations.add(convo)

        assignee = self.make_linear_member(issue.get('assignee'), channel, tstamp)
        if assignee is not None:
            participants.add(assignee)

        if issue.get('completedAt') and assignee is not None:
            completed_at = self.strptime(issue['completedAt'])
            contrib, created = Contribution.objects.update_or_create(
                origin_id=issue['id'],
                community=community,
                defaults={
                    'contribution_type': self.COMPLETED_CONTRIBUTION,
                    'channel': channel,
                    'author': assignee,
                    'timestamp': completed_at,
                    'title': ('%s %s' % (issue.get('identifier', ''), issue.get('title', ''))).strip()[:255],
                    'location': issue.get('url'),
                },
            )
            contrib.update_activity(convo.activity)
            if channel.tag:
                contrib.tags.add(channel.tag)
                convo.tags.add(channel.tag)
            convo.contribution = contrib
            convo.save()

        for comment in issue.get('comments', {}).get('nodes', []):
            comment_tstamp = self.strptime(comment['createdAt'])
            commenter = self.make_linear_member(comment.get('user'), channel, comment_tstamp, speaker=True)
            if commenter is None:
                continue
            body = (comment.get('body') or '').replace("\x00", "�")
            comment_convo = self.make_conversation(
                origin_id=comment['id'],
                channel=channel,
                speaker=commenter,
                content=body,
                tstamp=comment_tstamp,
                location=comment.get('url') or issue.get('url'),
                thread=convo,
            )
            participants.add(commenter)
            conversations.add(comment_convo)

        for c in conversations:
            self.add_participants(c, participants)
