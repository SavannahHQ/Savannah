from corm.plugins import BasePlugin, PluginImporter
from time import sleep
import datetime
import re
from corm.models import *
from urllib.parse import urlparse, parse_qs
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse
from django.urls import path
from django.contrib import messages
import requests
import json

USER_AGENT_STRING = "web:com.savannahcrm:1.1 (by /u/mhall119)"
AUTHORIZATION_BASE_URL = 'https://www.reddit.com/api/v1/authorize'
TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
REFRESH_URL = 'https://www.reddit.com/api/v1/access_token'

IDENTITY_URL = 'https://www.reddit.com/api/v1/me'
SUBREDDITS_DEFAULT_URL = 'https://oauth.reddit.com/subreddits/default'
SUBREDDITS_SEARCH_URL = 'https://oauth.reddit.com/subreddits/search'

POSTS_URL = 'https://oauth.reddit.com%(subreddit)snew?after=%(after)s&limit=100'
COMMENTS_URL = 'https://oauth.reddit.com%(subreddit)scomments/%(article)s?after=%(after)s&sort=new&threaded=0&limit=100'
MORE_CHILDREN_URL = 'https://oauth.reddit.com/api/morechildren?link=%(link)s&children=%(child_ids)s&limit_children=0&sort=new&limit=100'

USER_PROFILE_URL = 'https://oauth.reddit.com/user/%(user)s/about'

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    client_id = settings.REDDIT_CLIENT_ID
    reddit_auth_scope = [
        'identity',
        'read',
        'mysubreddits',
    ]
    callback_uri = request.build_absolute_uri(reverse('reddit_callback'))
    client = OAuth2Session(client_id, scope=reddit_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL, duration="permanent")

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    client_id = settings.REDDIT_CLIENT_ID
    client_secret = settings.REDDIT_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('reddit_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        ua_header = {
            'User-Agent': USER_AGENT_STRING
        }
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), auth=HTTPBasicAuth(client_id, client_secret), headers=ua_header)
        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, connector="corm.plugins.reddit", server="https://www.reddit.com", defaults={"auth_secret": token['access_token'], "auth_refresh": token.get('refresh_token', None)})
        source, created = Source.objects.update_or_create(community=community, auth_id=None, connector="corm.plugins.reddit", server="https://www.reddit.com", defaults={'name':"Reddit", 'icon_name': 'fab fa-reddit', 'auth_secret': token['access_token']})
        if created:
            messages.success(request, 'Your Reddit account has been connected!')
        else:
            messages.info(request, 'Your Reddit source has been updated.')

        return redirect(reverse('channels', kwargs={'community_id':community.id, 'source_id':source.id}))
    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect your Reddit account: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('auth', authenticate, name='reddit_auth'),
    path('callback', callback, name='reddit_callback'),
]

def refresh_auth(source):
    try:
        user_cred = UserAuthCredentials.objects.get(connector='corm.plugins.reddit', auth_secret=source.auth_secret, auth_refresh__isnull=False)
    except UserAuthCredentials.DoesNotExist:
        raise RuntimeError("Unable to refresh accesss token: Unknown credentials")
        
    try:
        client_id = settings.REDDIT_CLIENT_ID
        client_secret = settings.REDDIT_CLIENT_SECRET
        client = OAuth2Session(client_id)

        ua_header = {
            'User-Agent': USER_AGENT_STRING
        }
        new_token = client.refresh_token(REFRESH_URL, refresh_token=user_cred.auth_refresh, auth=HTTPBasicAuth(client_id, client_secret), headers=ua_header)
        user_cred.auth_secret = new_token.get('access_token')
        user_cred.save()
        source.auth_secret = new_token.get('access_token')
        source.save()
    except Exception as e:
        raise RuntimeError("Unable to refresh accesss token: %s" % e)

    return source

class RedditPlugin(BasePlugin):

    def get_identity_url(self, contact):
        if contact.origin_id:
            reddit_id = contact.origin_id.split("/")[-1]
            return "%s/u/%s" % (contact.source.server, reddit_id)
        else:
            return None

    def get_auth_url(self):
        return reverse('reddit_auth')

    def get_source_type_name(self):
        return "Reddit"

    def get_import_command_name(self):
        return "reddit"

    def get_source_importer(self, source):
        return RedditImporter(source)

    def search_channels(self, source, search):
        return self.get_channels(source, search)

    def get_channels(self, source, search=None):
        source = refresh_auth(source)
        channels = []
        auth_headers = {
            'User-Agent': USER_AGENT_STRING,
            "Authorization": "bearer %s" % source.auth_secret
        }
        if search is not None:
            resp = requests.get(SUBREDDITS_SEARCH_URL + '?limit=100,sort=relevance&q=%s'%search, headers=auth_headers)
        else:
            resp = requests.get(SUBREDDITS_DEFAULT_URL + '?limit=100', headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()

            for subreddit in data['data']['children']:
                channel = subreddit['data']
                if search and (search in channel['url'] or search in channel['display_name']):
                    channel['subscribers'] = channel.get('subscribers', 0) * 100000000
                    print(channel)
                channels.append(
                    {
                        'id': channel['url'],
                        'name': channel['display_name'],
                        'topic': channel['public_description'],
                        'count':channel.get('subscribers', 0) or 0,
                        'is_private': channel['subreddit_type'] in ("private", "restricted", "gold_restricted"),
                        'is_archived': channel['subreddit_type'] == "archived",
                        'is_favorite': channel.get('user_is_subscriber', False)
                    }
                )
        elif resp.status_code == 403:
            url = reverse('reddit_auth')
            raise RuntimeError("You may need to <a href=\"%s\">reauthorize Reddit</a>" % url)
        else:
            raise RuntimeError("%s (%s)" % (resp.reason, resp.status_code))

        return channels

class RedditImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(refresh_auth(source))
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
        self.API_HEADERS =  {
            'User-Agent': USER_AGENT_STRING,
            'Authorization': 'bearer %s' % source.auth_secret,
        }
        self._users = dict()
        self.tag_matcher = re.compile(r'\/u\/([a-zA-z0-9]+)')
        self._comment_cache = dict()

    def get_comment(self, comment_id):
        if comment_id in self._comment_cache:
            return self._comment_cache[comment_id]
        else:
            try:
                return Conversation.objects.get(origin_id=comment_id, channel__source=self.soruce)
            except:
                pass
        return None

    def strftime(self, dtime):
        return int(dtime.timestamp())

    def strptime(self, dtimestamp):
        return datetime.datetime.fromtimestamp(dtimestamp)

    def api_call(self, path):
        resp =  self.api_request(path, headers=self.API_HEADERS)
        if 'x-ratelimit-remaining' in resp.headers and float(resp.headers.get('x-ratelimit-remaining', 0)) < 10:
            print("API backoff, %s calls remaining" % resp.headers.get('x-ratelimit-remaining'))
            sleep(float(resp.headers.get('x-ratelimit-reset', 30)))
        if settings.DEBUG:
            print("API calls remaining: %s" % resp.headers.get('x-ratelimit-remaining'))
        return resp

    def get_user(self, user_id):
        if user_id in self._users:
            return self._users[user_id]
        resp = self.api_call(USER_PROFILE_URL % {'user': user_id})
        if resp.status_code == 200:
            data = resp.json()
            if data['kind'] == 't2':
                #print("User: %s" % data)
                self._users[user_id] = data['data']
                return self._users[user_id]
        return None

    def update_identity(self, identity):
        data = self.get_user(identity.origin_id.split('/')[-1])
        if data is not None:
            identity.name = data.get('name')
            identity.avatar_url = data.get('icon_img')
            identity.save()
        if identity.member.name == identity.detail and identity.name is not None:
            identity.member.name = identity.name
        if identity.member.email_address is None:
            identity.member.email_address = identity.email_address
        if identity.member.avatar_url is None:
            identity.member.avatar_url = identity.avatar_url
        identity.member.save()

    def import_channel(self, channel):
        if channel.last_import and not self.full_import:
            from_date = channel.last_import
        else:
            from_date = datetime.datetime.utcnow() - datetime.timedelta(days=180)
        print("From %s since %s" % (channel.name, from_date))

        self.from_timestamp = self.strftime(from_date)
        cursor = ''
        has_more = True
        while has_more:
            has_more = False
            resp = self.api_call(POSTS_URL % {'subreddit': channel.origin_id, 'after': cursor})
            if resp.status_code == 200:
                data = resp.json()
                if data['kind'] != "Listing":
                    print("Unknown response kind: %s" % data['kind'])
                    continue
                data = data['data']

                if data['after']:
                    has_more = True
                    cursor = data['after']
                for post in data['children']:
                    if post['kind'] != "t3":
                        print("Unknown post child kind: %s" % post)
                        continue
                    if post['data']['created_utc'] < self.from_timestamp:
                        has_more = False
                        break
                    self.import_post(channel, post['data'])
            else:
                print("HTTP %s Error: %s" % (resp.status_code, resp.content))

        return

    def import_post(self, channel, post):
        source = channel.source
        self._comment_cache = dict()

        tstamp = self.strptime(post['created_utc'])
        user_name = post['author']
        reddit_user_id = "/u/%s" % user_name
        speaker = self.make_member(reddit_user_id, channel=channel, detail=user_name, email_address=None, tstamp=tstamp, speaker=True, name=user_name)

        reddit_convo_id = post['name']
        reddit_convo_link = post['url']

        convo_text = post.get('selftext') or post.get('title')
        tagged = set(self.tag_matcher.findall(convo_text))

        convo = self.make_conversation(origin_id=reddit_convo_id, channel=channel, speaker=speaker, content=convo_text, tstamp=tstamp, location=reddit_convo_link)
        self._comment_cache[reddit_convo_id] = convo
        convo.participants.add(speaker)

        for tagged_user in tagged:
            try:
                tagged_user_id = "/u/%s" % tagged_user
                tagged_member = self.make_member(tagged_user_id, tagged_user)
                convo.participants.add(tagged_member)
                speaker.add_connection(tagged_member, source, tstamp)
            except:
                print("    Failed to find Contact for %s" % tagged_user)

        cursor = ''
        has_more = True
        while(has_more):
            has_more = False
            resp = self.api_call(COMMENTS_URL % {'subreddit': channel.origin_id, 'article': post['id'], 'after': cursor})
            if resp.status_code == 200:
                data = resp.json()[1]
                if data['kind'] != "Listing":
                    print("Unknown response kind: %s" % data['kind'])
                    continue
                data = data['data']

                if data['after']:
                    has_more = True
                    cursor = data['after']
                for comment in data['children']:
                    if comment['kind'] != "t1":
                        print("Unknown comment kind: %s" % comment)
                        continue
                    if comment['data']['created_utc'] < self.from_timestamp:
                        has_more = False
                        break
                    self.import_comment(channel, convo, comment['data'])
            else:
                print("HTTP %s Error: %s" % (resp.status_code, resp.content))

    def import_comment(self, channel, post, comment):
        source = channel.source

        tstamp = self.strptime(comment['created_utc'])
        user_name = comment['author']
        reddit_user_id = "/u/%s" % user_name
        speaker = self.make_member(reddit_user_id, channel=channel, detail=user_name, email_address=None, tstamp=tstamp, speaker=True, name=user_name)

        reddit_convo_id = comment['name']
        reddit_convo_link = "https://reddit.com%s" % comment['permalink']

        convo_text = comment.get('body')
        tagged = set(self.tag_matcher.findall(convo_text))

        thread = self.get_comment(comment.get('parent_id')) or post 
        convo = self.make_conversation(origin_id=reddit_convo_id, channel=channel, speaker=speaker, content=convo_text, tstamp=tstamp, location=reddit_convo_link, thread=thread)
        self._comment_cache[reddit_convo_id] = convo
        convo.participants.add(speaker)
        if thread.id != post.id and thread.speaker != convo.speaker:
            convo.participants.add(thread.speaker)
            thread.participants.add(speaker)
        if post.speaker != convo.speaker:
            convo.participants.add(post.speaker)
            post.participants.add(speaker)
            speaker.add_connection(post.speaker, source, tstamp)


        for tagged_user in tagged:
            try:
                tagged_user_id = "/u/%s" % tagged_user
                tagged_member = self.make_member(tagged_user_id, tagged_user)
                convo.participants.add(tagged_member)
                speaker.add_connection(tagged_member, source, tstamp)
            except:
                print("    Failed to find Contact for %s" % tagged_user)
