from corm.plugins import BasePlugin, PluginImporter
import datetime
import re
from corm.models import *
from urllib.parse import urlparse, parse_qs
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse
from django.urls import path
from django.contrib import messages
import requests

AUTHORIZATION_BASE_URL = 'https://slack.com/oauth/authorize'
TOKEN_URL = 'https://slack.com/api/oauth.access'
CONVERSATIONS_URL = 'https://slack.com/api/conversations.history?channel=%(channel)s&cursor=%(cursor)s&oldest=%(oldest)s'
CONVERSATION_LOOKUP = 'https://slack.com/api/conversations.history?channel=%(channel)s&latest=%(ts)s&limit=1&inclusive=1'
THREAD_URL = 'https://slack.com/api/conversations.replies?channel=%(channel)s&ts=%(thread_ts)s&cursor=%(cursor)s&oldest=%(oldest)s'
USER_PROFILE_URL = 'https://slack.com/api/users.info?user=%(user)s'
USERS_LIST = 'https://slack.com/api/users.list?cursor=%(cursor)s'

def authenticate(request):
    community = get_object_or_404(Community, id=request.session.get('community'))
    client_id = settings.SLACK_CLIENT_ID
    slack_auth_scope = [
        'channels:history',
        'channels:read',
        'users:read',
        'users:read.email',
        'groups:read',
        'groups:history',
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
    community = get_object_or_404(Community, id=request.session.get('community'))

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, connector="corm.plugins.slack", server=request.session['oauth_slack_instance'], defaults={"auth_id": token['user_id'], "auth_secret": token['access_token']})
        source, created = Source.objects.update_or_create(community=community, auth_id=token['team_id'], connector="corm.plugins.slack", server=request.session['oauth_slack_instance'], defaults={'name':token['team_name'], 'icon_name': 'fab fa-slack', 'auth_secret': token['access_token']})
        if created:
            messages.success(request, 'Your Slack workspace has been connected! Pick which channels you want to track from the list below.')
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

    def get_add_view(self):
        return authenticate
        
    def get_identity_url(self, contact):
        if contact.origin_id:
            slack_id = contact.origin_id.split("/")[-1]
            return "%s/team/%s" % (contact.source.server, slack_id)
        else:
            return None

    def get_icon_name(self):
        return 'fab fa-slack'

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
        resp = requests.get('https://slack.com/api/conversations.list?types=public_channel,private_channel&token=%s' % source.auth_secret)
        if resp.status_code == 200:
            data = resp.json()
            if data['ok'] == False:
                if data['error'] == 'missing_scope':
                    url = reverse('slack_auth')
                    raise RuntimeError("You may need to <a href=\"%s\">reauthorize Slack</a>" % url)
                raise RuntimeError(data['error'])
            for channel in data['channels']:
                channels.append(
                    {
                        'id': channel['id'],
                        'name': channel['name'],
                        'topic': channel['topic']['value'],
                        'count':channel.get('num_members', 0),
                        'is_private': channel['is_private'],
                        'is_archived': channel['is_archived'],
                    }
                )
        elif resp.status_code == 403:
            raise RuntimeError("Invalid authentication token")
        else:
            raise RuntimeError("%s (%s)" % (resp.reason, resp.status_code))

        return channels

class SlackImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
        self.API_HEADERS =  {
            'Authorization': 'Bearer %s' % source.auth_secret,
        }
        self._users = dict()
        self._has_prefetched = False
        self._update_threads = dict()
        self.tag_matcher = re.compile(r'\<\@([^>]+)\>')

    def api_call(self, path):
        return self.api_request(path, headers=self.API_HEADERS)

    def prefetch_users(self):
        if self._has_prefetched:
            return
        cursor = ''
        has_more = True
        self._has_prefetched = True
        while has_more:
            has_more = False
            resp = self.api_call(USERS_LIST % {'cursor': cursor})
            if resp.status_code == 200:
                data = resp.json()
                if data['ok']:
                    cursor = data['response_metadata'].get('next_cursor')
                    if cursor:
                        has_more = True
                    for user in data['members']:
                        self._users[user.get('id')] = user
                else:
                    print("prefetch_users failed: %s" % resp.content)
            else:
                print("prefetch_users failed: %s (%s) " % (resp.content, resp.status_code))

    def get_user(self, user_id):
        if user_id in self._users:
            return self._users[user_id]
        resp = self.api_call(USER_PROFILE_URL % {'user': user_id})
        if resp.status_code == 200:
            data = resp.json()
            if data['ok']:
                self._users[user_id] = data['user']
                return self._users[user_id]
        return None

    def update_identity(self, identity):
        data = self.get_user(identity.origin_id.split('/')[-1])
        if data is not None:
            identity.name = data.get('profile').get('real_name')            
            identity.email_address = data.get('profile').get('email')
            identity.avatar_url = data.get('profile').get('image_512')
            identity.save()
        if identity.member.name == identity.detail and identity.name is not None:
            identity.member.name = identity.name
        if identity.member.email_address is None:
            identity.member.email_address = identity.email_address
        if identity.member.avatar_url is None:
            identity.member.avatar_url = identity.avatar_url
        identity.member.save()

    def get_message(self, channel_id, msg_tstamp):
        resp = self.api_call(CONVERSATION_LOOKUP % {'channel': channel_id, 'ts': msg_tstamp})
        if resp.status_code == 200:
            data = resp.json()
            if data['ok']:
                return data['messages'][0]
        return None

    def import_channel(self, channel, from_date, full_import=False):
        self.prefetch_users()

        self._update_threads = dict()
        from_timestamp = from_date.timestamp()
        cursor = ''
        has_more = True
        while has_more:
            has_more = False
            resp = self.api_call(CONVERSATIONS_URL % {'channel': channel.origin_id, 'oldest': from_timestamp, 'cursor': cursor})
            if resp.status_code == 200:
                data = resp.json()
                if data['ok']:
                    if data['has_more']:
                        has_more = True
                        cursor = data['response_metadata']['next_cursor']
                    for message in data['messages']:
                        if message['type'] == 'message' and ('subtype' not in message or message['subtype'] == "bot_message"):
                            if 'thread_ts' in message:
                                self.import_thread(channel, message.get('thread_ts'), from_timestamp)
                            else:
                                self.import_message(channel, message)
                else:
                    print("Data Error: %s" % resp.content)
                    raise RuntimeError("Slack error: %s" % data.get('error', "Unknown Error"))
            else:
                print("HTTP %s Error: %s" % (resp.status_code, resp.content))
                raise RuntimeError("HTTP %s: %s" % (resp.status_code, resp.content))
        for thread_id, thread_ts in list(self._update_threads.items()):
            self.import_thread(channel, thread_ts, from_timestamp)
            # data = self.get_message(channel, thread_ts)
            # if data is not None:
            #     thread = Conversation.objects.get(channel=channel, id=thread_id)
            #     thread.content = data.get('text')
            #     thread.save()
        return

    def import_thread(self, channel, thread_ts, from_timestamp):
        cursor = ''
        has_more = True
        while has_more:
            has_more = False
            resp = self.api_call(THREAD_URL % {'channel': channel.origin_id, 'thread_ts': thread_ts, 'oldest': from_timestamp, 'cursor': cursor})
            if resp.status_code == 200:
                data = resp.json()
                if data['ok']:
                    if data['has_more']:
                        has_more = True
                        cursor = data['response_metadata']['next_cursor']
                        if self.verbosity >= 3:
                            print("Thread has_more=True, cursor=%s" % cursor)
                    for message in data['messages']:
                        if message['type'] == 'message' and ('subtype' not in message or message['subtype'] == "bot_message"):
                            self.import_message(channel, message)
                else:
                    print("Data Error: %s" % data)
                    raise RuntimeError("Slack error: %s" % data.get('error', "Unknown Error"))
            else:
                print("HTTP %s Error: %s" % (resp.status_code, resp.content))
                raise RuntimeError("HTTP %s: %s" % (resp.status_code, resp.content))
         
    def import_message(self, channel, message):
        source = channel.source

        tstamp = datetime.datetime.fromtimestamp(float(message.get('ts')))
        if message.get('subtype', None) == "bot_message":
            user_isbot = True
            user_id = message.get('bot_id')
            user_name = message.get('username', message.get('bot_id'))
            user_email = None
            user_real_name = user_name
        else:
            user = self.get_user(message['user'])
            user_isbot = False
            user_id = user.get('id')
            user_name = user.get('name', user.get('id'))
            user_email = user.get('profile').get('email')
            user_real_name = user.get('real_name', user_name)
        slack_user_id = "slack.com/%s" % user_id
        speaker = self.make_member(slack_user_id, channel=channel, detail=user_name, email_address=user_email, tstamp=tstamp, speaker=True, name=user_real_name)
        if user_isbot and speaker.role != Member.BOT:
            speaker.role = Member.BOT
            speaker.save()

        server = source.server or "slack.com"
        slack_convo_id = "%s/archives/%s/p%s" % (server, channel.origin_id, message.get('ts').replace(".", ""))
        slack_convo_link = slack_convo_id
        thread = None
        thread_participants = set()
        if 'thread_ts' in message:
            slack_convo_link = slack_convo_link + "?thread_ts=%s&cid=%s" % (message.get('thread_ts'), channel.origin_id)
            slack_thread_id = "%s/archives/%s/p%s" % (server, channel.origin_id, message.get('thread_ts').replace(".", ""))
            slack_thread_link = slack_thread_id + "?thread_ts=%s&cid=%s" % (message.get('thread_ts'), channel.origin_id)
            thread_tstamp = datetime.datetime.fromtimestamp(float(message.get('thread_ts')))
            thread = self.make_conversation(origin_id=slack_thread_id, channel=channel, speaker=speaker, tstamp=thread_tstamp, location=slack_thread_link)
            thread_participants = set(thread.participants.all())
            thread_participants.add(speaker)
            self._update_threads[thread.id] = message.get('thread_ts')

        convo_text = message.get('text')
        tagged = set(self.tag_matcher.findall(message.get('text')))
        for tagged_user_id in tagged:
            tagged_user = self.get_user(tagged_user_id)
            if tagged_user:
                convo_text = convo_text.replace("<@%s>"%tagged_user_id, "@%s"%tagged_user.get('real_name'))

        convo = self.make_conversation(origin_id=slack_convo_id, channel=channel, speaker=speaker, content=convo_text, tstamp=tstamp, location=slack_convo_link, thread=thread)
        convo_participants = set()
        convo_participants.add(speaker)
        if convo.id in self._update_threads:
            del self._update_threads[convo.id]

        for tagged_user in tagged:
            #if not slack._users.get(tagged_user):
                #print("Unknown Slack user: %s" % tagged_user)
                #continue
            #print("Checking for %s" % tagged_user)
            try:
                tagged_user_id = "slack.com/%s" % tagged_user
                #tagged_contact = Contact.objects.get(origin_id=tagged_user_id, source=source)
                tagged_member = self.make_member(tagged_user_id, tagged_user)
                convo_participants.add(tagged_member)
                if thread is not None:
                    thread_participants.add(tagged_member)
            except:
                print("    Failed to find Contact for %s" % tagged_user)

        # Connect this conversation's speaker to everyone else in this thread
        if thread is not None:
            self.add_participants(thread, thread_participants)
            if thread.participants.count() > 0:
                convo_participants.update(list(thread.participants.all()))

        self.add_participants(convo, convo_participants)
