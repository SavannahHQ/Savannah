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

FACEBOOK_API_ROOT = 'https://graph.facebook.com/v12.0'
FACEBOOK_SELF_URL = FACEBOOK_API_ROOT + '/me?fields=id,name,groups{name,administrator,member_count}'
FACEBOOK_GROUP_FEED = FACEBOOK_API_ROOT + '/%{group_id}/feed?fields=message,created_time,from,source,object_id,target,type,comments'
FACEBOOK_TIMESTAMP = '%Y-%m-%dT%H:%M:%SZ'

AUTHORIZATION_BASE_URL = 'https://www.facebook.com/v12.0/dialog/oauth'
TOKEN_URL = 'https://graph.facebook.com/v12.0/oauth/access_token'

class FacebookOrgForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['auth_id']
        labels = {
            'auth_id': 'Group',
        }
        widgets = {
            'auth_id': forms.Select(),
        }
    # class Media:
        # js = ('js/form_other_field.js',)
    
    def __init__(self, *args, **kwargs):
        super(FacebookOrgForm, self).__init__(*args, **kwargs)
        self.fields['auth_id'].required = True
        #self.fields['other'] = forms.CharField(label="Facebook URL", required=False)

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        try:
            cred = UserAuthCredentials.objects.get(user=request.user, connector="corm.plugins.facebook")
        except UserAuthCredentials.DoesNotExist:
            return authenticate(request)
        API_HEADERS =  {
            'Authorization': 'token %s' % cred.auth_secret,
        }

        if not cred.auth_id:
            resp = requests.get(FACEBOOK_SELF_URL, headers=API_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                cred.auth_id = data['login']
                cred.save()

        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.facebook", server="https://facebook.com", auth_id=cred.auth_id, auth_secret=cred.auth_secret, icon_name="fab fa-facebook")

        group_choices = []
        group_names = {}
        resp = requests.get(FACEBOOK_SELF_URL, headers=API_HEADERS, params={'access_token': cred.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            for grp in data['groups']['data']:
                if grp['administrator']:
                    group_choices.append((grp['id'], grp['name']))
                    group_names[grp['id']] = grp['name']
        else:
            messages.error(request, "Failed to retrieve Facebook groups: %s"%  resp.content)

        if request.method == "POST":
            form = FacebookOrgForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                source.name = group_names[source.auth_id]
                source.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        # org_choices.append(("other", "other..."))
        form = FacebookOrgForm(instance=new_source)
        form.fields['auth_id'].widget.choices = group_choices
        context = view.context
        context.update({
            "source_form": form,
            'source_plugin': 'Facebook',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, "savannahv2/source_add.html", context)

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    client_id = settings.FACEBOOK_CLIENT_ID
    facebook_auth_scope = [
        'groups_access_member_info',
        'public_profile',
    ]
    callback_uri = request.build_absolute_uri(reverse('facebook_callback'))
    client = OAuth2Session(client_id, scope=facebook_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    client_id = settings.FACEBOOK_CLIENT_ID
    client_secret = settings.FACEBOOK_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('facebook_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        cred, created = UserAuthCredentials.objects.get_or_create(user=request.user, connector="corm.plugins.facebook", server="https://facebook.com", defaults={"auth_secret": token['access_token']})

        return redirect('facebook_add')

    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect Facebook: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('add', SourceAdd.as_view, name='facebook_add'),
    path('auth', authenticate, name='facebook_auth'),
    path('callback', callback, name='facebook_callback'),
]

class FacebookPlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_identity_url(self, contact):
        return "https://facebook.com/%s" % contact.detail

    def get_company_url(self, group):
        if group.origin_id[0] == '@':
            return "https://facebook.com/%s" % group.origin_id[1:]
        else:
            return None

    def get_icon_name(self):
        return 'fab fa-facebook'

    def get_auth_url(self):
        return reverse('facebook_auth')

    def get_source_type_name(self):
        return "Facebook"

    def get_import_command_name(self):
        return "facebook"


    def get_source_importer(self, source):
        return FacebookImporter(source)

    def get_channels(self, source):
        channels = [
            {'id': 'members', 'name': 'Members', 'topic': 'Member names and joined dates', 'count':10},
            {'id': 'discussions', 'name': 'Discussions', 'topic': 'Posts and comments', 'count':9},
            {'id': 'events', 'name': 'Events', 'topic': 'Events and attendees', 'count':8},
        ]

        return channels

class FacebookImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_PARAMS =  {
            'access_token': source.auth_secret,
        }
        self.TIMESTAMP_FORMAT = FACEBOOK_TIMESTAMP
        # self.PR_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Pull Request")
        # feedback, created = ContributionType.objects.get_or_create(
        #     community=source.community,
        #     source_id=source.id,
        #     name="Feedback",
        # )

    def api_call(self, path):
        return self.api_request(path, params=self.API_PARAMS)

    # def update_identity(self, identity):
    #     resp = self.api_call(FACEBOOK_USER_URL%{'username':identity.detail})
    #     if resp.status_code == 200:
    #         data = resp.json()
    #         identity.name = data['name']            
    #         identity.email_address = data['email']
    #         identity.avatar_url = data['avatar_url']
    #         identity.save()

    #         if identity.member.name == identity.detail and identity.name is not None:
    #             identity.member.name = identity.name
    #         if identity.member.email_address is None:
    #             identity.member.email_address = identity.email_address

    #         if identity.member.company is None and data.get("company") is not None:
    #             origin_id = data.get("company").split(" @")[0].strip()
    #             try:
    #                 group = SourceGroup.objects.get(origin_id=origin_id, source=self.source)
    #                 identity.member.company = group.company
    #             except:
    #                 company_name = origin_id.replace('@', '')
    #                 company = Company.objects.create(community=self.source.community, name=company_name)
    #                 SourceGroup.objects.create(origin_id=origin_id, company=company, source=self.source, name=company_name)
    #                 identity.member.company = company
    #         identity.member.save()
    #     else:
    #         print("Failed to lookup identity info: %s" % resp.content)

    def import_channel(self, channel, from_date, full_import=False):
      source = channel.source
      community = source.community
      raise RuntimeError("Not implemented")