import datetime
import re
from urllib.parse import urlencode
import requests
import json
from pytwitter import Api as TwitterClient
from requests_oauthlib import OAuth2Session
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.contrib import messages
from django import forms

from corm.plugins import BasePlugin, PluginImporter
from corm.models import *
from frontendv2.views import SavannahView

AUTHORIZATION_BASE_URL = 'https://twitter.com/i/oauth2/authorize'
TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
TWITTER_ME_URL = 'https://api.twitter.com/2/users/me'
TWITTER_USER_LOOKUP = 'https://api.twitter.com/2/users/by?user.fields=profile_image_url'
TWITTER_USER_TIMELINE = 'https://api.twitter.com/2/users/%s/tweets?max_results=50'
TWITTER_SEARCH_URL = 'https://api.twitter.com/2/tweets/search/recent?max_results=50'
TWITTER_MENTIONS = 'https://api.twitter.com/2/tweets/search/recent?query=%(username)s&tweet.fields=created_at,in_reply_to_user_id,referenced_tweets,conversation_id&expansions=author_id,referenced_tweets.id,in_reply_to_user_id&max_results=50'
TWITTER_MENTIONS_PAGED = 'https://api.twitter.com/2/tweets/search/recent?query=%(username)s&tweet.fields=created_at,in_reply_to_user_id,referenced_tweets,conversation_id&expansions=author_id,referenced_tweets.id,in_reply_to_user_id&pagination_token=%(pagination_token)s&max_results=50'

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    client_id = settings.TWITTER_CLIENT_ID
    client_secret = settings.TWITTER_CLIENT_SECRET
    twitter_auth_scope = [
        'tweet.read',
        'users.read',
        'follows.read',
        'space.read',
        'offline.access'
    ]
    callback_uri = request.build_absolute_uri(reverse('twitter_callback'))
    client = TwitterClient(client_id=client_id, callback_uri=callback_uri, scopes=twitter_auth_scope, oauth_flow=True)
    authorization_url, code_verifier, state = client.get_oauth2_authorize_url()

    request.session['oauth_state'] = state
    request.session['oauth_code_verifier'] = code_verifier
    return redirect(authorization_url)


def callback(request):
    client_id = settings.TWITTER_CLIENT_ID
    client_secret = settings.TWITTER_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('twitter_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), auth=HTTPBasicAuth(client_id, client_secret), code_verifier=request.session['oauth_code_verifier'])
        
        resp = requests.get(TWITTER_ME_URL, headers={'Authorization': 'Bearer %s' % token['access_token']})
        me = resp.json()['data']
        # print(me)

        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, auth_id=me['username'], connector="corm.plugins.twitter", server="https://twitter.com", defaults={"auth_secret": token['access_token'], 'auth_refresh': token['refresh_token']})
        source, created = Source.objects.update_or_create(community=community, auth_id=me['username'], connector="corm.plugins.twitter", server="https://api.twitter.com", defaults={'name':me['name'], 'icon_name': 'fab fa-twitter', 'auth_secret': token['access_token']})
        if created:
            messages.success(request, 'Your Twitter account has been connected!')
        else:
            messages.info(request, 'Your Twitter source has been updated.')

        return redirect(reverse('channels', kwargs={'community_id':community.id, 'source_id':source.id}))

    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect Twitter: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('auth', authenticate, name='twitter_auth'),
    path('callback', callback, name='twitter_callback'),
]

def refresh_auth(source):
    try:
        user_cred = UserAuthCredentials.objects.get(connector='corm.plugins.twitter', auth_id=source.auth_id, auth_secret=source.auth_secret, auth_refresh__isnull=False)
    except UserAuthCredentials.DoesNotExist:
        raise RuntimeError("Unable to refresh accesss token: Unknown credentials")
        
    try:
        client_id = settings.TWITTER_CLIENT_ID
        client_secret = settings.TWITTER_CLIENT_SECRET
        client = OAuth2Session(client_id)

        new_token = client.refresh_token(TOKEN_URL, refresh_token=user_cred.auth_refresh, auth=HTTPBasicAuth(client_id, client_secret), client_id=client_id)
        user_cred.auth_secret = new_token.get('access_token')
        user_cred.auth_refresh = new_token.get('refresh_token')
        user_cred.save()
        source.auth_secret = new_token.get('access_token')
        source.save()
    except Exception as e:
        raise RuntimeError("Unable to refresh accesss token: %s" % e)

    return source

class TwitterPlugin(BasePlugin):

    def get_add_view(self):
        return authenticate

    def get_identity_url(self, contact):
        return "https://www.twitter.com/%s" % contact.detail

    def get_channel_url(self, channel):
        if channel.name[0] == '@':
            return "https://www.twitter.com/%s" % channel.name[1:]
        else:
            return 'https://twitter.com/search?q=%%23%s' % channel.name[1:]

    def get_company_url(self, group):
        return None

    def get_icon_name(self):
        return 'fab fa-twitter'

    def get_auth_url(self):
        return reverse('twitter_auth')

    def get_source_type_name(self):
        return "Twitter"

    def get_import_command_name(self):
        return "twitter"


    def get_source_importer(self, source):
        return TwitterImporter(source)

    def search_channels(self, source, text):
        source = refresh_auth(source)
        matching = []

        resp = requests.get(TWITTER_SEARCH_URL, params={'query': text}, headers={'Authorization': 'Bearer %s' % source.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            # print(data)
            recent_tags = dict()
            recent_mentions = dict()
            if 'data' not in data:
                return matching
            for tweet in data['data']:
                tags = re.findall('#[a-zA-Z0-9]+', tweet['text'])
                for tag in tags:
                    tag = tag.lower()
                    if tag in recent_tags:
                        recent_tags[tag] += 1
                    else:
                        recent_tags[tag] = 1
                mentions = re.findall('@[a-zA-Z0-9]+', tweet['text'])
                for username in mentions:
                    username = username.lower()
                    if username in recent_mentions:
                        recent_mentions[username] += 1
                    else:
                        recent_mentions[username] = 1
            for username, count in sorted(recent_mentions.items(), key=lambda c: c[1], reverse=True)[:5]:
                matching.append({'id': username, 'topic': 'Tweets that mention '+username, 'name': username, 'count':count})
            for tag, count in recent_tags.items():
                matching.append({'id': tag, 'topic': 'Tweets tagged with '+tag, 'name': tag, 'count':count})
            if text.startswith('@'):
                username = text.split(' ')[0]
                if username not in recent_mentions:
                    matching.append({'id': username, 'topic': 'Tweets that mention '+username, 'name': username, 'count':1000000})
            return matching
        else:
            raise RuntimeError("Hashtag search failed: %s" % resp.content)

    def get_channels(self, source):
        source = refresh_auth(source)
        channels =  [{'id': '@'+source.auth_id, 'topic': 'Tweets that mention @'+source.auth_id, 'name': '@'+source.auth_id, 'count':1000000}]

        resp = requests.get(TWITTER_USER_LOOKUP, params={'usernames': source.auth_id}, headers={'Authorization': 'Bearer %s' % source.auth_secret})
        data = resp.json()
        # print(data)
        if resp.status_code != 200:
            raise RuntimeError(data['detail'])
        me = data['data'][0]
        # print(me)

        resp = requests.get(TWITTER_USER_TIMELINE % me['id'], headers={'Authorization': 'Bearer %s' % source.auth_secret})
        data = resp.json()
        recent_tags = dict()
        for tweet in data['data']:
            tags = re.findall('#[a-zA-Z0-9]+', tweet['text'])
            for tag in tags:
                tag = tag.lower()
                if tag in recent_tags:
                    recent_tags[tag] += 1
                else:
                    recent_tags[tag] = 1
        for tag, count in recent_tags.items():
            channels.append({'id': tag, 'topic': 'Tweets tagged with '+tag, 'name': tag, 'count':count})
        return channels

    def get_channel_add_warning(self, channel):
        if channel.name.startswith('#'):
            return "<h4><b>Be careful about what hashtags you track!</b></h4>You should only track hashtags that are unique to your community. Tracking generic hashtags will lead to the importation of members and conversations who are not really part of your community."

class TwitterImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
        self.API_HEADERS =  {
            'Authorization': 'Bearer %s' % source.auth_secret,
            'Content-Type': 'application/json',
        }
        self._users = dict()

    def api_call(self, path):
        resp =  self.api_request(path, headers=self.API_HEADERS)
        return resp

    def get_user(self, user_id):
        # print("Looking up user: %s" % user_id)
        if user_id in self._users:
            return self._users[user_id]
        resp = requests.get(TWITTER_USER_LOOKUP, params={'usernames': user_id}, headers={'Authorization': 'Bearer %s' % self.source.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            self._users[user_id] = data['data'][0]
            return self._users[user_id]
        else:
            print("Failed to lookup identity info: %s" % resp.content)
        return None

    def update_identity(self, identity):
        data = self.get_user(identity.detail)
        if data is not None:
            identity.name = data['name']            
            identity.avatar_url = data['profile_image_url']
            identity.save()

        if identity.member.name == identity.detail and identity.name is not None:
            identity.member.name = identity.name
        if identity.member.avatar_url is None:
            identity.member.avatar_url = identity.avatar_url
        identity.member.save()

    def update_source(self):
        self.source = refresh_auth(self.source)
        self.API_HEADERS['Authorization'] = 'Bearer %s' % self.source.auth_secret

    def get_tagged_users(self, content):
        tagged_users = set()
        tag_matcher = re.compile(r'\@([a-zA-Z0-9_]+)')
        for tagged_username in tag_matcher.findall(content):
            tagged_user = self.get_user(tagged_username)
            if tagged_user:
                tagged_user_id = "slack.com/%s" % tagged_user
                #tagged_contact = Contact.objects.get(origin_id=tagged_user_id, source=source)
                tagged_member = self.make_member(tagged_user['id'], detail=tagged_username)
                tagged_users.add(tagged_member)
            else:
                print("Failed to find tagged user: %s" % tagged_user)
        return tagged_users

    def import_channel(self, channel, from_date, full_import=False):
        source = channel.source
        community = source.community
        if channel.origin_id[0] == '@':
            self.import_mentions(channel, from_date, full_import)
        if channel.origin_id[0] == '#':
            self.import_hashtag(channel, from_date, full_import)

    def import_mentions(self, channel, from_date, full_import):
        self.from_date = self.strftime(from_date)
        cursor = ''
        has_more = True
        while has_more:
            has_more = False
            if cursor:
                resp = self.api_call(TWITTER_MENTIONS_PAGED % {'username': channel.origin_id, 'pagination_token': cursor})
            else:
                resp = self.api_call(TWITTER_MENTIONS % {'username': channel.origin_id})
            if resp.status_code == 200:
                if self.verbosity >= 3:
                    print(resp.content)
                data = resp.json()
                users = dict()
                replied_to = dict()
                if 'includes' in data:
                    for user in data['includes']['users']:
                        users[user['id']] = user
                    if 'tweets' in data['includes']:
                        for tweet in data['includes']['tweets']:
                            replied_to[tweet['id']] = tweet

                for tweet in data['data']:
                    if tweet['text'].startswith('RT'):
                        continue

                    tstamp = self.strptime(tweet['created_at'])
                    if tstamp < from_date and not full_import:
                        continue
                    has_more = True

                    thread = None
                    if tweet.get('conversation_id', None) and tweet['conversation_id'] != tweet['id'] and tweet['conversation_id'] in replied_to:
                        parent = replied_to[tweet['conversation_id']]
                        parent_tstamp = self.strptime(parent['created_at'])
                        parent_user = users[parent['author_id']]
                        parent_speaker = self.make_member(parent_user['id'], detail=parent_user['username'], name=parent_user.get('name', parent_user['username']), avatar_url=parent_user.get('profile_image_url', None), speaker=True)
                        parent_url = 'https://twitter.com/%s/status/%s' % (parent_user['username'], parent['id'])
                        thread = self.make_conversation(tweet['conversation_id'], channel=channel, speaker=parent_speaker, tstamp=parent_tstamp, location=parent_url, content=parent['text'])

                    user = users[tweet['author_id']]
                    speaker = self.make_member(user['id'], detail=user['username'], name=user.get('name', user['username']), avatar_url=user.get('profile_image_url', None), speaker=True)
                    tweet_url = 'https://twitter.com/%s/status/%s' % (user['username'], tweet['id'])
                    convo = self.make_conversation(tweet['id'], channel=channel, speaker=speaker, content=tweet['text'], tstamp=tstamp, location=tweet_url, thread=thread)
                    if thread:
                        self.add_participants(convo, thread.participants.all())
                        self.make_participant(thread, speaker)
                if has_more and 'next_token' in data['meta'] and data['meta']['next_token'] != cursor:
                    cursor = data['meta']['next_token']
                else:
                    has_more = False
            else:
                print(resp.content)
                raise RuntimeError("Failed to retreive mentions")

    def import_hashtag(self, channel, from_date, full_import):
        self.from_date = self.strftime(from_date)
        cursor = ''
        has_more = True
        hashtag = '%23'+channel.origin_id[1:]
        while has_more:
            has_more = False
            if cursor:
                resp = self.api_call(TWITTER_MENTIONS_PAGED % {'username': hashtag, 'pagination_token': cursor})
            else:
                resp = self.api_call(TWITTER_MENTIONS % {'username': hashtag})
            if resp.status_code == 200:
                if self.verbosity >= 3:
                    print(resp.content)
                data = resp.json()
                users = dict()
                replied_to = dict()
                if 'includes' in data:
                    for user in data['includes']['users']:
                        users[user['id']] = user
                    if 'tweets' in data['includes']:
                        for tweet in data['includes']['tweets']:
                            replied_to[tweet['id']] = tweet

                for tweet in data['data']:
                    if tweet['text'].startswith('RT'):
                        continue

                    tstamp = self.strptime(tweet['created_at'])
                    if tstamp < from_date and not full_import:
                        continue
                    has_more = True

                    thread = None
                    if tweet.get('conversation_id', None) and tweet['conversation_id'] != tweet['id'] and tweet['conversation_id'] in replied_to:
                        parent = replied_to[tweet['conversation_id']]
                        parent_tstamp = self.strptime(parent['created_at'])
                        parent_user = users[parent['author_id']]
                        parent_speaker = self.make_member(parent_user['id'], detail=parent_user['username'], name=parent_user.get('name', parent_user['username']), avatar_url=parent_user.get('profile_image_url', None), speaker=True)
                        parent_url = 'https://twitter.com/%s/status/%s' % (parent_user['username'], parent['id'])
                        thread = self.make_conversation(tweet['conversation_id'], channel=channel, speaker=parent_speaker, tstamp=parent_tstamp, location=parent_url, content=parent['text'])

                    user = users[tweet['author_id']]
                    speaker = self.make_member(user['id'], detail=user['username'], name=user.get('name', user['username']), avatar_url=user.get('profile_image_url', None), speaker=True)
                    tweet_url = 'https://twitter.com/%s/status/%s' % (user['username'], tweet['id'])
                    convo = self.make_conversation(tweet['id'], channel=channel, speaker=speaker, content=tweet['text'], tstamp=tstamp, location=tweet_url, thread=thread, dedup=True)
                if has_more and 'next_token' in data['meta'] and data['meta']['next_token'] != cursor:
                    cursor = data['meta']['next_token']
                else:
                    has_more = False
            else:
                print(resp.content)
                raise RuntimeError("Failed to retreive tagged tweets")
