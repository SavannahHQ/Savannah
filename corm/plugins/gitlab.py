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

GITLAB_TIMESTAMP = '%Y-%m-%dT%H:%M:%SZ'

AUTHORIZATION_BASE_URL = 'https://gitlab.com/oauth/authorize'
TOKEN_URL = 'https://gitlab.com/oauth/token'
GITLAB_OWNER_GROUPS_URL = 'https://gitlab.com/api/v4/groups?min_access_level=10'
GITLAB_GROUP_URL = 'https://gitlab.com/api/v4/groups/%(group_id)s'
GITLAB_GROUP_PROJECTS_URL = 'https://gitlab.com/api/v4/groups/%(group_id)s/projects?include_subgroups=true'

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
                    source.auth_id = url_parts[1]
                    source.name = source.auth_id
                resp = requests.get(GITLAB_GROUP_URL % {'group_id': source.auth_id})
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
            'source_plugin': 'Github',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, "savannahv2/source_add.html", context)

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
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

    def get_identity_url(self, contact):
        pass#return "https://github.com/%s" % contact.detail

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
        resp = requests.get(GITLAB_GROUP_PROJECTS_URL % {'group_id': source.auth_id}, headers=headers)   
        if resp.status_code == 200:
            data = resp.json()
            for repo in data:
                channels.append({
                    'id': repo.get('web_url'),
                    'name': repo.get('name_with_namespace'),
                    'topic': repo.get('description'),
                    'count': repo.get('last_activity_at'),
                })
        else:
            print("Request failed: %s" % resp.content)
            data = resp.json()
            raise RuntimeError(data.get('message'))
        return channels

class GitlabImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Authorization': 'Bearer %s' % source.auth_secret,
        }
        self.TIMESTAMP_FORMAT = GITLAB_TIMESTAMP
        self.PR_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Pull Request")

    def api_call(self, path):
        if settings.DEBUG:
            print("API Call: %s" % path)
        return self.api_request(path, headers=self.API_HEADERS)

    def update_identity(self, identity):
        pass

    def import_channel(self, channel):
        source = channel.source
        community = source.community
        pass