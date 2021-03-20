import datetime
import re
import requests
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.contrib import messages
from django import forms

from corm.plugins import BasePlugin, PluginImporter
from corm.models import *
from frontendv2.views import SavannahView

GITLAB_TIMESTAMP = '%Y-%m-%dT%H:%M:%S.%fZ'

AUTHORIZATION_BASE_URL = 'https://gitlab.com/oauth/authorize'
TOKEN_URL = 'https://gitlab.com/oauth/token'
GITLAB_OWNER_GROUPS_URL = 'https://gitlab.com/api/v4/groups?min_access_level=10'
GITLAB_GROUP_URL = '/api/v4/groups/%(group_id)s'
GITLAB_GROUP_PROJECTS_URL = '/api/v4/groups/%(group_id)s/projects?include_subgroups=true'
GITLAB_ISSUES_URL = '/api/v4/projects/%(project_id)s/issues?order_by=updated_at&updated_after=%(updated_after)s'
GITLAB_ISSUE_COMMENTS = '/api/v4/projects/%(project_id)s/issues/%(iid)s/discussions'
GITLAB_MR_URL = '/api/v4/projects/%(project_id)s/merge_requests?order_by=updated_at&updated_after=%(updated_after)s'
GITLAB_MR_COMMENTS = '/api/v4/projects/%(project_id)s/merge_requests/%(iid)s/discussions'


class GitlabGroupForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['auth_id']
        labels = {
            'auth_id': 'Group',
        }
        widgets = {
            'auth_id': forms.Select(),
        }
    class Media:
        js = ('js/form_other_field.js',)
    
    def __init__(self, *args, **kwargs):
        super(GitlabGroupForm, self).__init__(*args, **kwargs)
        self.fields['auth_id'].required = True
        self.fields['other'] = forms.CharField(label="Gitlab URL", required=False)

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        try:
            cred = UserAuthCredentials.objects.get(user=request.user, connector="corm.plugins.gitlab")
        except UserAuthCredentials.DoesNotExist:
            return authenticate(request)
        API_HEADERS =  {
            'Authorization': 'Bearer %s' % cred.auth_secret,
        }

        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.gitlab", server="https://gitlab.com", auth_id=cred.auth_id, auth_secret=cred.auth_secret, icon_name="fab fa-gitlab")

        if request.method == "POST":
            form = GitlabGroupForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                if source.auth_id == 'other':
                    github_url = form.cleaned_data['other']
                    if github_url.startswith('https://'):
                        github_url = github_url[8:]
                    url_parts = github_url.split('/')
                    source.server = "https://%s" % url_parts[0]
                    source.auth_id = url_parts[1]
                    source.name = source.auth_id
                resp = requests.get(source.server + GITLAB_GROUP_URL % {'group_id': source.auth_id})
                if resp.status_code == 200:
                    group = resp.json()
                    source.name = group['name']
                source.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        org_choices = []
        resp = requests.get(GITLAB_OWNER_GROUPS_URL, headers=API_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            for org in data:
                org_choices.append((org['path'], org['name']))
        else:
            messages.error(request, "Failed to retrieve Gitlab orgs: %s"%  resp.content)
        org_choices.append(("other", "other..."))
        form = GitlabGroupForm(instance=new_source)
        form.fields['auth_id'].widget.choices = org_choices
        context = view.context
        context.update({
            "source_form": form,
            'source_plugin': 'Gitlab',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, "savannahv2/source_add.html", context)

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    if not community.management.can_add_source():
        messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
        return redirect('sources', community_id=community.id)
    client_id = settings.GITLAB_CLIENT_ID
    gitlab_auth_scope = [
        'read_user',
        'read_api'
    ]
    callback_uri = request.build_absolute_uri(reverse('gitlab_callback'))
    client = OAuth2Session(client_id, scope=gitlab_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    client_id = settings.GITLAB_CLIENT_ID
    client_secret = settings.GITLAB_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('gitlab_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        cred, created = UserAuthCredentials.objects.get_or_create(user=request.user, connector="corm.plugins.gitlab", server="https://gitlab.com", defaults={"auth_secret": token['access_token']})

        return redirect('gitlab_add')

    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect Gitlab: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('add', SourceAdd.as_view, name='gitlab_add'),
    path('auth', authenticate, name='gitlab_auth'),
    path('callback', callback, name='gitlab_callback'),
]

class GitlabPlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_identity_url(self, contact):
        return contact.origin_id

    def get_icon_name(self):
        return 'fab fa-gitlab'

    def get_auth_url(self):
        return reverse('gitlab_auth')

    def get_source_type_name(self):
        return "Gitlab"

    def get_import_command_name(self):
        return "gitlab"


    def get_source_importer(self, source):
        return GitlabImporter(source)

    def get_channels(self, source):
        channels = []
        headers = {'Authorization': 'Bearer %s' % source.auth_secret}
        resp = requests.get(source.server + GITLAB_GROUP_PROJECTS_URL % {'group_id': source.auth_id}, headers=headers)   
        if resp.status_code == 200:
            data = resp.json()
            for project in data:
                channels.append({
                    'id': str(project.get('id')),
                    'name': project.get('name'),
                    'topic': project.get('description'),
                    'count': project.get('last_activity_at'),
                })
        else:
            print("Request failed: %s" % resp.content)
            data = resp.json()
            raise RuntimeError(data)
        return channels

class GitlabImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Authorization': 'Bearer %s' % source.auth_secret,
        }
        self.TIMESTAMP_FORMAT = GITLAB_TIMESTAMP
        self.PR_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Merge Request")

    def update_identity(self, identity):
        pass

    def import_channel(self, channel, from_date, full_import=False):
        source = channel.source
        community = source.community
        
        updated_after = self.strftime(from_date)
        resp = self.api_call(GITLAB_ISSUES_URL % {'project_id': channel.origin_id, 'updated_after': updated_after})
        if resp.status_code == 200:
            data = resp.json()
            for issue in data:
                self.import_comments(source, channel, issue, GITLAB_ISSUE_COMMENTS)

        resp = self.api_call(GITLAB_MR_URL % {'project_id': channel.origin_id, 'updated_after': updated_after})
        if resp.status_code == 200:
            data = resp.json()
            for mr in data:
                self.import_comments(source, channel, mr, GITLAB_MR_COMMENTS)

    def import_comments(self, source, channel, issue, comments_url):
        issue_iid = issue.get('iid')
        project_id = issue.get('project_id')
        thread_tstamp = self.strptime(issue.get('created_at'))
        connection_tstamp = self.strptime(issue.get('updated_at'))
        gitlab_convo_link = issue.get('web_url')

        participants = set()
        conversations = set()

        thread_author = issue.get('author')
        thread_user_id = thread_author.get('web_url')
        thread_speaker = self.make_member(origin_id=thread_user_id, channel=channel, detail=thread_author.get('username'), tstamp=thread_tstamp, avatar_url=thread_author.get('avatar_url'), name=thread_author.get('name'), speaker=True)
        participants.add(thread_speaker)

        thread_text = issue.get('description')
        tagged = self.get_user_tags(thread_text)
        for tagged_user in tagged:
            tagged_origin_id = "%s/%s" % (source.server, tagged_user)
            if tagged_origin_id in self._member_cache:
                participants.add(self._member_cache[tagged_origin_id])
            else:
                try:
                    tagged_contact = Contact.objects.get(origin_id=tagged_origin_id, source=source)
                    participants.add(tagged_contact.member)
                except:
                    pass
                    #Matched tag doesn't correspond to a known user                       
        thread_url = gitlab_convo_link
        thread = self.make_conversation(issue.get('id'), channel=channel, speaker=thread_speaker, content=thread_text, tstamp=thread_tstamp, location=thread_url, thread=None)
        conversations.add(thread)

        # Merge Requests are a Contribution
        if comments_url == GITLAB_MR_COMMENTS:
            author = issue.get('author')
            gitlab_user_id = author.get('web_url')
            submitter = self.make_member(origin_id=gitlab_user_id, detail=author.get('username'), channel=channel, tstamp=thread_tstamp, avatar_url=author.get('avatar_url'), name=author.get('name'), speaker=True)
            
            activity, created = Contribution.objects.update_or_create(origin_id=issue.get('iid'), community=source.community, defaults={'contribution_type':self.PR_CONTRIBUTION, 'channel':channel, 'author':submitter, 'timestamp':thread_tstamp, 'title':issue.get('title'), 'location':gitlab_convo_link})
            # Not all comments should get the channel tag, but all PRs should
            if channel.tag:
                activity.tags.add(channel.tag)
                thread.tags.add(channel.tag)
            thread.contribution = activity
            thread.save()
        else:
            activity = None

        comments = issue.get('user_notes_count')
        if comments > 0:
            resp = self.api_call(comments_url % {'project_id': project_id, 'iid': issue_iid})
            if resp.status_code == 200:
                data = resp.json()
                for notes in data:
                    for note in notes.get('notes'):
                        convo_tstamp = self.strptime(note.get('created_at'))
                        author = note.get('author')
                        gitlab_user_id = author.get('web_url')
                        speaker = self.make_member(origin_id=gitlab_user_id, detail=author.get('username'), channel=channel, tstamp=convo_tstamp, avatar_url=author.get('avatar_url'), name=author.get('name'), speaker=True)
                        participants.add(speaker)

                        convo_text = note.get('body')
                        tagged = self.get_user_tags(convo_text)
                        for tagged_user in tagged:
                            tagged_origin_id = "%s/%s" % (source.server, tagged_user)
                            if tagged_origin_id in self._member_cache:
                                participants.add(self._member_cache[tagged_origin_id])
                            else:
                                try:
                                    tagged_contact = Contact.objects.get(origin_id=tagged_origin_id, source=source)
                                    participants.add(tagged_contact.member)
                                except:
                                    pass
                                    #Matched tag doesn't correspond to a known user                       
                        convo_url = "%s#note_%s" % (gitlab_convo_link, note.get('id'))
                        convo = self.make_conversation(note.get('id'), channel=channel, speaker=speaker, content=convo_text, tstamp=convo_tstamp, location=convo_url, thread=thread)
                        conversations.add(convo)



        # Add everybody involved as a participant in every conversation
        for convo in conversations:
            self.add_participants(convo, participants)
