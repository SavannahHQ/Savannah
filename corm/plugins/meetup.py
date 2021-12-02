import datetime
import re
import requests
import json
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.contrib import messages
from django import forms

from corm.plugins import BasePlugin, PluginImporter
from corm.models import *
from frontendv2.views import SavannahView

AUTHORIZATION_BASE_URL = 'https://secure.meetup.com/oauth2/authorize'
TOKEN_URL = 'https://secure.meetup.com/oauth2/access'
MEETUP_API_ROOT = 'https://api.meetup.com/gql'
MEETUP_SELF_QUERY = '{"query": "query { self { id name isAdmin memberships{ edges{ node{id name isPrivate isOrganizer } } } } }"}'
MEETUP_MEMBERS_QUERY = 'query($groupId: ID) {group(id: $groupId) { name memberships { count pageInfo { endCursor } edges { node { id name email joinTime } } } } }'
MEETUP_MEMBERS_QUERY_PAGED = 'query($groupId: ID, $cursor: String!) {group(id: $groupId) { name memberships(input: {after: $cursor}) { count pageInfo { endCursor } edges { node { id name email joinTime } } } } }'
MEETUP_PAST_EVENTS_QUERY = '''
  query($groupId:ID) {
    group(id: $groupId) {
      pastEvents(input: {first:20}) {
        count
        pageInfo { endCursor }
        edges {
          node {
            id
            title
            dateTime
            endTime
            eventUrl
            hosts { id name }
            tickets {
              edges {
                node {
                  user { id name }
                }
              }
            }
            shortDescription
            description
          }
        }
      }
      
    }
  }
  '''
class MeetupOrgForm(forms.ModelForm):
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
        super(MeetupOrgForm, self).__init__(*args, **kwargs)
        self.fields['auth_id'].required = True
        #self.fields['other'] = forms.CharField(label="Meetup URL", required=False)

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        try:
            cred = UserAuthCredentials.objects.get(user=request.user, connector="corm.plugins.meetup")
        except UserAuthCredentials.DoesNotExist:
            return authenticate(request)
        API_HEADERS =  {'Authorization': 'Bearer %s' % cred.auth_secret, 'Content-Type': 'application/json'}

        if not cred.auth_id:
            resp = requests.post(MEETUP_API_ROOT, data=MEETUP_SELF_QUERY, headers=API_HEADERS)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    cred.auth_id = data['data']['self']['id']
                    cred.save()
                except:
                    messages.error(request, "Failed to update Meetup account details")
        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.meetup", server="https://meetup.com", auth_id=cred.auth_id, auth_secret=cred.auth_secret, icon_name="fab fa-meetup")

        group_choices = []
        group_names = {}
        resp = requests.post(MEETUP_API_ROOT, data=MEETUP_SELF_QUERY, headers=API_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            for grp in data['data']['self']['memberships']['edges']:
                group_choices.append((grp['node']['id'], grp['node']['name']))
                group_names[grp['node']['id']] = grp['node']['name']
        else:
            messages.error(request, "Failed to retrieve Meetup groups: %s"%  resp.content)

        if request.method == "POST":
            form = MeetupOrgForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                source.name = group_names[source.auth_id]
                source.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        # org_choices.append(("other", "other..."))
        form = MeetupOrgForm(instance=new_source)
        form.fields['auth_id'].widget.choices = group_choices
        context = view.context
        context.update({
            "source_form": form,
            'source_plugin': 'Meetup',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, "savannahv2/source_add.html", context)

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    client_id = settings.MEETUP_CLIENT_ID
    meetup_auth_scope = [

    ]
    callback_uri = request.build_absolute_uri(reverse('meetup_callback'))
    client = OAuth2Session(client_id, scope=meetup_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    client_id = settings.MEETUP_CLIENT_ID
    client_secret = settings.MEETUP_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('meetup_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri, include_client_id=True)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        cred, created = UserAuthCredentials.objects.get_or_create(user=request.user, connector="corm.plugins.meetup", server="https://meetup.com", defaults={"auth_secret": token['access_token']})

        return redirect('meetup_add')

    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect Meetup: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('add', SourceAdd.as_view, name='meetup_add'),
    path('auth', authenticate, name='meetup_auth'),
    path('callback', callback, name='meetup_callback'),
]

class MeetupPlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_identity_url(self, contact):
        return "https://www.meetup.com/members/%s" % contact.origin_id

    def get_company_url(self, group):
        return None

    def get_icon_name(self):
        return 'fab fa-meetup'

    def get_auth_url(self):
        return reverse('meetup_auth')

    def get_source_type_name(self):
        return "Meetup"

    def get_import_command_name(self):
        return "meetup"


    def get_source_importer(self, source):
        return MeetupImporter(source)

    def get_channels(self, source):
        channels = [
            # {'id': 'members', 'name': 'Members', 'topic': 'Member names and joined dates', 'count':10},
            {'id': 'discussions', 'name': 'Discussions', 'topic': 'Posts and comments', 'count':9},
            {'id': 'events', 'name': 'Events', 'topic': 'Events and attendees', 'count':8},
        ]

        return channels

class MeetupImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Authorization': 'Bearer %s' % source.auth_secret,
            'Content-Type': 'application/json',
        }
        if settings.USE_TZ:
            self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M%z'
        else:
            self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M'
        self.HOST_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Hosted")
        self.SPEAKER_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Speaker")

    def strptime(self, timestamp):
        if settings.USE_TZ:
            if ":" == timestamp[-3:-2]:
                timestamp = timestamp[:-3]+timestamp[-2:]
        else:
            timestamp = timestamp[:-6]
        return super().strptime(timestamp)

    def api_call(self, query, **variables):
        data = json.dumps({
            "query": query,
            "variables": variables
        })
        print("API Call: %s" % data)
        return requests.post(MEETUP_API_ROOT, data=data, headers=self.API_HEADERS)

    # def update_identity(self, identity):
    #     resp = self.api_call(MEETUP_USER_URL%{'username':identity.detail})
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
        if channel.origin_id == 'members':
            self.import_members(from_date, full_import)
        elif channel.origin_id == 'events':
            self.import_events(channel, from_date, full_import)
        elif channel.origin_id == 'discussions':
            self.import_discussions(channel, from_date, full_import)
        else:
            raise RuntimeError("Unknown Meetup channel: %s" % channel.id)

    def import_members(self, from_date, full_import=False):
        cursor = None
        has_more = True
        while has_more:
            has_more = False
            if cursor:
                resp = self.api_call(MEETUP_MEMBERS_QUERY_PAGED, groupId=self.source.auth_id, cursor=cursor)
            else:
                resp = self.api_call(MEETUP_MEMBERS_QUERY, groupId=self.source.auth_id)
            if resp.status_code == 200:
                data = resp.json()
                # print(data)
                for m in data['data']['group']['memberships']['edges']:
                    user = m['node']
                    member = self.make_member(user['id'], detail=user['name'])
                if cursor != data['data']['group']['memberships']['pageInfo']['endCursor']:
                    cursor = data['data']['group']['memberships']['pageInfo']['endCursor']
                    has_more = True
                
        else:
            raise RuntimeError("Error querying members: %s" % resp.content)

    def import_events(self, channel, from_date, full_import=False):
        if full_import:
            resp = self.api_call(MEETUP_PAST_EVENTS_QUERY, groupId=self.source.auth_id)
            if resp.status_code == 200:
                data = resp.json()
                for e in data['data']['group']['pastEvents']['edges']:
                    try:
                        event = e['node']
                        origin_id = event['id'].split('!')[0]
                        start_date = self.strptime(event['dateTime'])
                        end_date = self.strptime(event['endTime'])
                        new_event = self.make_event(origin_id=origin_id, channel=channel, title=event['title'], description=event['description'], start=start_date, end=end_date, location=event['eventUrl'])

                        for rsvp in event['tickets']['edges']:
                            user = rsvp['node']['user']
                            user_id = user['id'].split('!')[0]
                            attendee = self.make_member(user_id, user['name'], tstamp=start_date)
                            self.add_event_attendee(new_event, attendee)

                        for host in event['hosts']:
                            host_id = host['id'].split('!')[0]
                            h = self.make_member(host_id, host['name'], tstamp=start_date)
                            attendee = self.add_event_attendee(new_event, h, EventAttendee.HOST)
                            contrib, contrib_created = Contribution.objects.get_or_create(
                                community=self.community,
                                channel=channel,
                                author=h,
                                contribution_type=self.HOST_CONTRIBUTION,
                                timestamp=new_event.start_timestamp,
                                defaults={
                                    'location': new_event.location,
                                    'title': 'Hosted %s' % new_event.title,
                                }
                            )
                            contrib.update_activity(attendee.activity)
                    except Exception as e:
                        print(e)
                        
        else:
            raise RuntimeError("Not implemented")

    def import_discussions(self, channel, from_date, full_import=False):
        raise RuntimeError("Not implemented")
