from corm.plugins import BasePlugin, PluginImporter
import datetime
import re
from perceval.backends.core.slack import Slack
from corm.models import Community, Source, Member, Contact, Channel, Conversation
from urllib.parse import urlparse, parse_qs
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse
from django.urls import path
from django.contrib import messages
import requests

AUTHORIZATION_BASE_URL = 'https://slack.com/oauth/authorize'
TOKEN_URL = 'https://slack.com/api/oauth.access'

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    client_id = settings.SLACK_CLIENT_ID
    slack_auth_scope = [
        'channels:history',
        'channels:read',
        'users:read',
    ]
    callback_uri = request.build_absolute_uri(reverse('slack_callback'))
    client = OAuth2Session(client_id, scope=slack_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)
    url = urlparse(authorization_url)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    request.session['oauth_slack_instance'] = url.scheme + '://' + url.netloc
    return redirect(authorization_url)


def callback(request):
    client_id = settings.SLACK_CLIENT_ID
    client_secret = settings.SLACK_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('slack_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        print(token)
        source, created = Source.objects.update_or_create(community=community, connector="corm.plugins.slack", server=request.session['oauth_slack_instance'], defaults={'name':token['team_name'], 'icon_name': 'fab fa-slack', 'auth_secret': token['access_token']})
        if created:
            messages.success(request, 'Your Slack workspace has been connected!')
        else:
            messages.info(request, 'Your Slack source has been updated.')

        return redirect(reverse('channels', kwargs={'community_id':community.id, 'source_id':source.id}))
    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect your Slack workspace: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('auth', authenticate, name='slack_auth'),
    path('callback', callback, name='slack_callback'),
]

class SlackPlugin(BasePlugin):

    def get_identity_url(self, contact):
        if contact.origin_id:
            slack_id = contact.origin_id.split("/")[-1]
            return "%s/team/%s" % (contact.source.server, slack_id)
        else:
            return None

    def get_auth_url(self):
        return reverse('slack_auth')

    def get_source_type_name(self):
        return "Slack"

    def get_import_command_name(self):
        return "slack"

    def get_source_importer(self, source):
        return SlackImporter(source)

    def get_channels(self, source):
        channels = []
        resp = requests.get('https://slack.com/api/conversations.list?token=%s' % source.auth_secret)
        if resp.status_code == 200:
            data = resp.json()
            for channel in data['channels']:
                if not channel['is_archived'] and not channel['is_private']:
                    channels.append(
                        {
                            'id': channel['id'],
                            'name': channel['name'],
                            'topic': channel['topic']['value'],
                            'count':channel['num_members'],
                        }
                    )
        return channels

class SlackImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

    def import_channel(self, channel):
        source = channel.source
        community = source.community
        if channel.last_import and not self.full_import:
            from_date = channel.last_import
        else:
            from_date = datetime.datetime.utcnow() - datetime.timedelta(days=180)
        print("From %s since %s" % (channel.name, from_date))
        slack = Slack(channel.origin_id, channel.source.auth_secret)
        items = [i for i in slack.fetch(from_date=from_date)]
        for slack_id, user in slack._users.items():
            if not user.get('is_bot'):
                slack_user_id = "slack.com/%s" % slack_id
                member = self.make_member(slack_user_id, detail=user.get('name'), tstamp=datetime.datetime.now(), name=user.get('real_name', user.get('name')))

        tag_matcher = re.compile('\<\@([^>]+)\>')
        for item in items:
            if item.get('data').get('subtype') is None and item.get('data').get('user_data'):
                tagged = set(tag_matcher.findall(item.get('data').get('text')))

                # We only want to check comments that tag somebody else, or are part of a thread
                if len(tagged) > 0 or 'thread_ts' in item.get('data'):
                    #print("Importing conversation from %s" % item.get('data').get('user_data').get('name'))
                    slack_user_id = "slack.com/%s" % item.get('data').get('user_data').get('id')
                    member = self.make_member(slack_user_id, item.get('data').get('user_data').get('name'), speaker=True)
                    #contact = Contact.objects.get(origin_id=slack_user_id, source=source)
                    tstamp = datetime.datetime.fromtimestamp(float(item.get('data').get('ts')))
                    server = source.server or "slack.com"
                    slack_convo_id = "%s/archives/%s/p%s" % (server, channel.origin_id, item.get('data').get('ts').replace(".", ""))
                    slack_convo_link = slack_convo_id
                    thread = None
                    if 'thread_ts' in item.get('data'):
                        slack_convo_link = slack_convo_link + "?thread_ts=%s&cid=%s" % (item.get('data').get('thread_ts'), channel.origin_id)
                        slack_thread_id = "%s/archives/%s/p%s" % (server, channel.origin_id, item.get('data').get('thread_ts').replace(".", ""))
                        slack_thread_link = slack_thread_id + "?thread_ts=%s&cid=%s" % (item.get('data').get('thread_ts'), channel.origin_id)
                        thread_tstamp = datetime.datetime.fromtimestamp(float(item.get('data').get('ts')))
                        thread, created = Conversation.objects.get_or_create(origin_id=slack_thread_id, channel=channel, defaults={'timestamp':thread_tstamp, 'location': slack_thread_link})
                        thread.participants.add(member)

                    convo_text = item.get('data').get('text')
                    for tagged_user in tagged:
                        if slack._users.get(tagged_user):
                            convo_text = convo_text.replace("<@%s>"%tagged_user, "@%s"%slack._users.get(tagged_user).get('real_name'))
                    convo_text = convo_text
                    try:
                        convo, created = Conversation.objects.update_or_create(origin_id=slack_convo_id, channel=channel, defaults={'speaker':member, 'channel':channel, 'content':convo_text, 'timestamp':tstamp, 'location':slack_convo_link, 'thread_start':thread})
                    except:
                        pass#import pdb; pdb.set_trace()
                    convo.participants.add(member)

                    for tagged_user in tagged:
                        #if not slack._users.get(tagged_user):
                            #print("Unknown Slack user: %s" % tagged_user)
                            #continue
                        #print("Checking for %s" % tagged_user)
                        try:
                            tagged_user_id = "slack.com/%s" % tagged_user
                            #tagged_contact = Contact.objects.get(origin_id=tagged_user_id, source=source)
                            tagged_member = self.make_member(tagged_user_id, tagged_user)
                            convo.participants.add(tagged_member)
                            if thread is not None:
                                thread.participants.add(tagged_member)
                            member.add_connection(tagged_member, source, tstamp)
                        except:
                            print("    Failed to find Contact for %s" % tagged_user)

                    # Connect this conversation's speaker to everyone else in this thread
                    if thread is not None:
                        for thread_member in thread.participants.all():
                            try:
                                member.add_connection(thread_member, source, tstamp)
                                convo.participants.add(thread_member)
                            except Exception as e:
                                print("    Failed to make connection between %s and %s" % (member, tagged_contact.member))
                                print(e)
