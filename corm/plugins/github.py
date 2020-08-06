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

GITHUB_SELF_URL = 'https://api.github.com/user'
GITHUB_USER_URL = 'https://api.github.com/users/%(username)s'
GITHUB_OWNER_ORGS_URL = 'https://api.github.com/user/orgs'
GITHUB_MEMBER_ORGS_URL = 'https://api.github.com/users/%(username)s/orgs'
GITHUB_ISSUES_URL = 'https://api.github.com/repos/%(owner)s/%(repo)s/issues?state=all&since=%(since)s&page=%(page)s'
GITHUB_REPOS_URL = 'https://api.github.com/orgs/%(owner)s/repos?sort=pushed&direction=desc&page=%(page)s'
GITHUB_TIMESTAMP = '%Y-%m-%dT%H:%M:%SZ'

AUTHORIZATION_BASE_URL = 'https://github.com/login/oauth/authorize'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
INSTALLATIONS_URL = 'https://api.github.com/user/installations'

class GithubOrgForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['auth_id']
        labels = {
            'auth_id': 'Organization',
        }
        widgets = {
            'auth_id': forms.Select(),
        }
    class Media:
        js = ('js/form_other_field.js',)
    
    def __init__(self, *args, **kwargs):
        super(GithubOrgForm, self).__init__(*args, **kwargs)
        self.fields['auth_id'].required = True
        self.fields['other'] = forms.CharField(label="Github URL", required=False)

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        try:
            cred = UserAuthCredentials.objects.get(user=request.user, connector="corm.plugins.github")
        except UserAuthCredentials.DoesNotExist:
            return authenticate(request)
        API_HEADERS =  {
            'Authorization': 'token %s' % cred.auth_secret,
        }

        if not cred.auth_id:
            resp = requests.get(GITHUB_SELF_URL, headers=API_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                cred.auth_id = data['login']
                cred.save()

        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.github", server="https://github.com", auth_id=cred.auth_id, auth_secret=cred.auth_secret, icon_name="fab fa-github")

        if request.method == "POST":
            form = GithubOrgForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                if source.auth_id == 'other':
                    github_url = form.cleaned_data['other']
                    if github_url.startswith('https://'):
                        github_url = github_url[8:]
                    url_parts = github_url.split('/')
                    source.auth_id = url_parts[1]
                source.name = source.auth_id
                source.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        org_choices = []
        resp = requests.get(GITHUB_OWNER_ORGS_URL, headers=API_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            for org in data:
                org_choices.append((org['login'], org['login']))
        else:
            messages.error(request, "Failed to retrieve Github orgs: %s"%  resp.content)
        resp = requests.get(GITHUB_MEMBER_ORGS_URL % {'username': cred.auth_id}, headers=API_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            for org in data:
                org_choices.append((org['login'], org['login']))
        else:
            messages.error(request, "Failed to retrieve Github orgs: %s"%  resp.content)
        org_choices.append(("other", "other..."))
        form = GithubOrgForm(instance=new_source)
        form.fields['auth_id'].widget.choices = org_choices
        context = view.context
        context.update({
            "source_form": form,
            'source_plugin': 'Github',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, "savannahv2/source_add.html", context)

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    client_id = settings.GITHUB_CLIENT_ID
    github_auth_scope = [
        'read:org',
        'public_repo',
    ]
    callback_uri = request.build_absolute_uri(reverse('github_callback'))
    client = OAuth2Session(client_id, scope=github_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    client_id = settings.GITHUB_CLIENT_ID
    client_secret = settings.GITHUB_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('github_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        cred, created = UserAuthCredentials.objects.get_or_create(user=request.user, connector="corm.plugins.github", server="https://github.com", defaults={"auth_secret": token['access_token']})

        return redirect('github_add')

    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect Github: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('add', SourceAdd.as_view, name='github_add'),
    path('auth', authenticate, name='github_auth'),
    path('callback', callback, name='github_callback'),
]

class GithubPlugin(BasePlugin):

    def get_identity_url(self, contact):
        return "https://github.com/%s" % contact.detail

    def get_auth_url(self):
        return reverse('github_auth')

    def get_source_type_name(self):
        return "Github"

    def get_import_command_name(self):
        return "github"


    def get_source_importer(self, source):
        return GithubImporter(source)

    def get_channels(self, source):
        channels = []
        page = 0
        has_more = True
        headers = {'Authorization': 'token %s' % source.auth_secret}
        while has_more:
            page += 1
            has_more = False
            resp = requests.get(GITHUB_REPOS_URL % {'owner': source.auth_id, 'page': page}, headers=headers)   
            if resp.status_code == 200:
                data = resp.json()
                for repo in data:
                    print(repo)
                    has_more = True
                    channels.append({
                        'id': repo.get('html_url'),
                        'name': repo.get('name'),
                        'topic': repo.get('description'),
                        'count': repo.get('updated_at'),
                        'is_private': repo.get('private'),
                        'is_archived': repo.get('archived'),
                    })
            else:
                print("Request failed: %s" % resp.content)
                data = resp.json()
                raise RuntimeError(data.get('message'))
        return channels

class GithubImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Authorization': 'token %s' % source.auth_secret,
        }
        self.TIMESTAMP_FORMAT = GITHUB_TIMESTAMP
        self.PR_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Pull Request")

    def api_call(self, path):
        return self.api_request(path, headers=self.API_HEADERS)

    def update_identity(self, identity):
        resp = self.api_call(GITHUB_USER_URL%{'username':identity.detail})
        if resp.status_code == 200:
            data = resp.json()
            identity.name = data['name']            
            identity.email_address = data['email']
            identity.avatar_url = data['avatar_url']
            identity.save()

            if identity.member.name == identity.detail and identity.name is not None:
                identity.member.name = identity.name
            if identity.member.email_address is None:
                identity.member.email_address = identity.email_address
            identity.member.save()
        else:
            print("Failed to lookup identity info: %s" % resp.content)

    def import_channel(self, channel):
      source = channel.source
      community = source.community
      github_path = channel.origin_id.split('/')

      owner = github_path[3]
      repo = github_path[4]
      if channel.last_import and not self.full_import:
        from_date = channel.last_import.strftime(GITHUB_TIMESTAMP)
      else:
        from_date = datetime.datetime.utcnow() - datetime.timedelta(days=180)
      print("  since %s" % from_date)

      tag_matcher = re.compile('\@([a-zA-Z0-9]+)')
      found_members = dict()

      issues_page = 1
      while (issues_page):
        repo_issues_url = GITHUB_ISSUES_URL % {'owner': owner, 'repo': repo, 'since': from_date, 'page': issues_page}
            
        resp = self.api_call(repo_issues_url)
        if resp.status_code == 200:
            issues = resp.json()
            for issue in issues:

                participants = set()
                conversations = set()
                tstamp = datetime.datetime.strptime(issue['created_at'], GITHUB_TIMESTAMP)
                github_convo_link = issue['url']

                # Add Member
                github_user_id = 'github.com/%s' % issue['user']['login']
                member = self.make_member(github_user_id, detail=issue['user']['login'], tstamp=tstamp, name=issue['user']['login'], speaker=True)

                # Pull Requests are an Activity
                if 'pull_request' in issue:
                    activity, created = Contribution.objects.update_or_create(origin_id=github_convo_link, community=community, defaults={'contribution_type':self.PR_CONTRIBUTION, 'channel':channel, 'author':member, 'timestamp':tstamp, 'title':issue['title'], 'location':issue['html_url']})
                    # Not all comments should get the channel tag, but all PRs should
                    if channel.tag:
                        activity.tags.add(channel.tag)
                else:
                    activity = None

                # If there are comments it's a Conversation
                if issue.get('comments', 0) > 0:
                    convo, created = Conversation.objects.update_or_create(origin_id=github_convo_link, channel__source=source, defaults={'channel':channel, 'speaker':member, 'content':issue['body'], 'timestamp':tstamp, 'location':issue['html_url']})
                    conversations.add(convo)
                    if activity:
                        activity.conversation = convo
                        activity.save()

                    participants.add(member)

                    comment_resp = self.api_call(issue['comments_url'])
                    if comment_resp.status_code == 200:
                        comments = comment_resp.json()
                        for comment in comments:
                            comment_tstamp = datetime.datetime.strptime(comment['created_at'], GITHUB_TIMESTAMP)
                            comment_user_id = 'github.com/%s' % comment['user']['login']
                            comment_member = self.make_member(comment_user_id, detail=comment['user']['login'], tstamp=comment_tstamp, name=comment['user']['login'], speaker=True)
                            comment_convo, created = Conversation.objects.update_or_create(origin_id=comment['url'], defaults={'channel':channel, 'speaker':comment_member, 'content':comment['body'], 'timestamp':comment_tstamp, 'location':comment['html_url'], 'thread_start':convo})
                            participants.add(comment_member)
                            conversations.add(comment_convo)
                            tagged = set(tag_matcher.findall(comment['body']))
                            if tagged:
                                for tagged_user in tagged:
                                    if tagged_user in found_members:
                                        participants.add(found_members[tagged_user])
                                    else:
                                        try:
                                            tagged_user_id = "github.com/%s" % tagged_user
                                            tagged_contact = Contact.objects.get(origin_id=tagged_user_id, source=source)
                                            participants.add(tagged_contact.member)
                                        except:
                                            pass#print("    Failed to find Contact for %s" % tagged_user)


                try:
                    tagged = set(tag_matcher.findall(issue['body']))
                    if tagged:
                        for tagged_user in tagged:
                            tagged_user_id = 'github.com/%s' % tagged_user
                            if tagged_user_id in self._member_cache:
                                participants.add(self._member_cache[tagged_user_id])
                            else:
                                try:
                                    tagged_contact = Contact.objects.get(origin_id=tagged_user_id, source=source)
                                    participants.add(tagged_contact.member)
                                except:
                                    pass#print("    Failed to find Contact for %s" % tagged_user)
                except:
                    pass

                # Add everybody involved as a participant in every conversation
                for convo in conversations:
                    convo.participants.set(participants)

                # Connect all participants
                for from_member in participants:
                    for to_member in participants:
                        if from_member.id != to_member.id:
                            from_member.add_connection(to_member, source, tstamp)


        # If there are more pages of issues, continue on to the next apge
        if 'link' in resp.headers and 'rel="next"' in resp.headers['link']:
            issues_page+= 1
        else:
            break