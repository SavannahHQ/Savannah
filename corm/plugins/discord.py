from corm.plugins import BasePlugin, PluginImporter
import datetime
import re
import pytz
from corm.models import *
from frontendv2.views import SavannahView
from urllib.parse import urlparse, parse_qs
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.contrib import messages
from django import forms
import requests

AUTHORIZATION_BASE_URL = 'https://discord.com/api/oauth2/authorize'
TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_SELF_URL = 'https://discord.com/api/users/@me'
DISCORD_GUILDS_URL = 'https://discord.com/api/users/@me/guilds'
DISCORD_GUILD_URL = 'https://discord.com/api/guilds/%(guild)s'

CONVERSATIONS_URL = 'https://discord.com/api/channels/%(channel)s/messages'
CONVERSATIONS_NEXT_URL = 'https://discord.com/api/channels/%(channel)s/messages?before=%(lastpost)s'

DISCORD_THREADS_URL = 'https://discord.com/api/guilds/%(guild)s/threads/active'

class DiscordOrgForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['auth_id']
        labels = {
            'auth_id': 'Server',
        }
        widgets = {
            'auth_id': forms.Select(),
        }
    class Media:
        js = ('js/form_other_field.js',)
    
    def __init__(self, *args, **kwargs):
        super(DiscordOrgForm, self).__init__(*args, **kwargs)
        self.fields['auth_id'].required = True
        self.fields['other'] = forms.CharField(label="Discord URL", required=False)

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        try:
            cred = UserAuthCredentials.objects.get(user=request.user, connector="corm.plugins.discord")
        except UserAuthCredentials.DoesNotExist:
            return authenticate(request)
        API_HEADERS =  {
            'Authorization': 'Bearer %s' % cred.auth_secret,
        }

        if not cred.auth_id:
            resp = requests.get(DISCORD_SELF_URL, headers=API_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                cred.auth_id = data['id']
                cred.save()

        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.discord", server="https://discord.com", auth_id=cred.auth_id, auth_secret=cred.auth_secret, icon_name="fab fa-discord")

        org_choices = []
        org_map = dict()
        resp = requests.get(DISCORD_GUILDS_URL, headers=API_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            for org in data:
                org_choices.append((org['id'], org['name']))
                org_map[org['id']] = org['name']
        else:
            messages.error(request, "Failed to retrieve Discord orgs: %s"%  resp.content)

        if request.method == "POST":
            form = DiscordOrgForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                source.name = org_map[source.auth_id]
                source.save()
                messages.success(request, 'Your Discord server has been connected! Pick which channels you want to track from the list below.')
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        form = DiscordOrgForm(instance=new_source)
        form.fields['auth_id'].widget.choices = org_choices
        context = view.context
        context.update({
            "source_form": form,
            'source_plugin': 'Discord',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
            'switch_account_url': reverse('discord_switch_account')
        })
        return render(request, "savannahv2/source_add.html", context)

def switch(request):
    community = get_object_or_404(Community, id=request.session['community'])
    UserAuthCredentials.objects.filter(user=request.user, connector="corm.plugins.discord").delete()
    return authenticate(request)


def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    if not community.management.can_add_source():
        messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
        return redirect('sources', community_id=community.id)

    client_id = settings.DISCORD_CLIENT_ID
    discord_auth_scope = [
        'bot',
        'guilds',
    ]
    callback_uri = request.build_absolute_uri(reverse('discord_callback'))
    client = OAuth2Session(client_id, scope=discord_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)
    url = urlparse(authorization_url)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    request.session['oauth_discord_instance'] = url.scheme + '://' + url.netloc
    return redirect(authorization_url)


def callback(request):
    client_id = settings.DISCORD_CLIENT_ID
    client_secret = settings.DISCORD_APP_SECRET
    callback_uri = request.build_absolute_uri(reverse('discord_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, connector="corm.plugins.discord", server=request.session['oauth_discord_instance'], defaults={"auth_secret": token['access_token']})
        source, created = Source.objects.update_or_create(community=community, connector="corm.plugins.discord", icon_name="fab fa-discord", server=request.session['oauth_discord_instance'], auth_id=token['guild']['id'], defaults={'name':token['guild'].get('name', token['guild']['id']), "auth_secret": settings.DISCORD_BOT_SECRET})
        messages.success(request, 'Your Discord server has been connected! Pick which channels you want to track from the list below.')
        return redirect('channels', community_id=community.id, source_id=source.id)


    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect your Discord workspace: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('add', SourceAdd.as_view, name='discord_add'),
    path('auth', authenticate, name='discord_auth'),
    path('callback', callback, name='discord_callback'),
    path('switch', switch, name='discord_switch_account'),
]

class DiscordPlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_identity_url(self, contact):
        if contact.origin_id:
            discord_id = contact.origin_id.split("/")[-1]
            return "%s/team/%s" % (contact.source.server, discord_id)
        else:
            return None

    def get_icon_name(self):
        return 'fab fa-discord'
        
    def get_auth_url(self):
        return reverse('discord_auth')

    def get_source_type_name(self):
        return "Discord"

    def get_import_command_name(self):
        return "discord"

    def get_source_importer(self, source):
        return DiscordImporter(source)

    def get_channels(self, source):
        channels = []
        headers = {'Authorization': 'Bot %s' % source.auth_secret}
        DISCORD_CHANNELS_URL = 'https://discord.com/api/guilds/%(guild)s/channels'
        resp = requests.get(DISCORD_CHANNELS_URL % {'guild': source.auth_id}, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            for channel in data:
                if channel['type'] == 0:
                    channels.append(
                        {
                            'id': channel['id'],
                            'name': channel['name'],
                            'topic': channel.get('topic', ''),
                            'count':len(data) - channel.get('position', 0),
                            'is_private': False,
                            'is_archived': False,
                        }
                    )

        elif resp.status_code == 403:
            raise RuntimeError("Invalid authentication token")
        else:
            raise RuntimeError("%s (%s)" % (resp.reason, resp.status_code))

        return channels

class DiscordImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S'
        self.API_HEADERS =  {
            'Authorization': 'Bot %s' % source.auth_secret,
        }
        support, created = ContributionType.objects.get_or_create(
            community=source.community,
            source_id=source.id,
            name="Support",
        )
        feedback, created = ContributionType.objects.get_or_create(
            community=source.community,
            source_id=source.id,
            name="Feedback",
        )
        
    def api_call(self, path):
        return self.api_request(path, headers=self.API_HEADERS)

    def import_channel(self, channel, from_date, full_import=False):
        cursor = None
        has_more = True
        utc = pytz.timezone('UTC')
        while has_more:
            if cursor:
                url = CONVERSATIONS_NEXT_URL % {'channel': channel.origin_id, 'lastpost': cursor}
            else:
                url = CONVERSATIONS_URL % {'channel': channel.origin_id}

            has_more = False
            cursor = None
            resp = self.api_call(url)
            if resp.status_code == 200:
                data = resp.json()

                for message in data:

                    try:
                        if message['type'] == 0:
                            # Ignore Discord timestamps after the second, because they don't use a consistent format
                            tstamp_str = message.get('timestamp')[:19]
                            tstamp = self.strptime(tstamp_str)
                            if self.full_import or tstamp >= from_date:
                                self.import_message(channel, message, tstamp)
                                has_more = True
                                cursor = message['id']
                    except Exception as e:
                        print("Failed to import message: %s" % e)
                        print(message)
                        raise e
            else:
                print("Failed to get conversations: %s" % resp.content)

        return

    def post_import(self, new_only, channels):
        if self.verbosity >= 2:
            print("Importing Threads...")
        tracked_channels = dict([(c.origin_id, c) for c in channels])
        resp = self.api_call(DISCORD_THREADS_URL % {'guild': self.source.auth_id})
        if resp.status_code == 200:
            data = resp.json()        
            for thread in data['threads']:
                if thread.get('parent_id', None) in tracked_channels:
                    archive_timestamp = self.strptime(thread['thread_metadata']['archive_timestamp'][:19])
                    self.import_thread(thread, tracked_channels[thread.get('parent_id')])

    def import_thread(self, thread, channel, from_date=None):
        if not from_date:
            from_date = self.source.last_import
        cursor = None
        has_more = True
        # Override the channel's origin_id to be the thread's ID
        channel.origin_id = thread.get('id')
        while has_more:
            if cursor:
                url = CONVERSATIONS_NEXT_URL % {'channel': channel.origin_id, 'lastpost': cursor}
            else:
                url = CONVERSATIONS_URL % {'channel': channel.origin_id}

            has_more = False
            cursor = None
            resp = self.api_call(url)
            if resp.status_code == 200:
                data = resp.json()

                participants = set()
                for message in data:

                    try:
                        if message['type'] == 0:
                            # Ignore Discord timestamps after the second, because they don't use a consistent format
                            tstamp_str = message.get('timestamp')[:19]
                            tstamp = self.strptime(tstamp_str)
                            if self.full_import or tstamp >= from_date:
                                self.import_message(channel, message, tstamp, participants=participants)
                                has_more = True
                                cursor = message['id']
                    except Exception as e:
                        print("Failed to import message: %s" % e)
                        print(message)
                        raise e
            else:
                print("Failed to get conversations: %s" % resp.content)

        return

    def import_message(self, channel, message, tstamp, participants=None):
        source = channel.source

        if participants is None:
            participants = set()
        user = message['author']
        discord_user_id = user.get('id')
        avatar_hash = user.get('avatar')
        avatar_url = 'https://cdn.discordapp.com/avatars/%s/%s.png?size=64' % (discord_user_id, avatar_hash)
        speaker = self.make_member(discord_user_id, channel=channel, detail=user.get('username'), avatar_url=avatar_url, email_address=user.get('email'), tstamp=tstamp, speaker=True, name=user.get('username'))
        if (user.get('bot', False) or user.get('system', False))and speaker.role != Member.BOT:
            speaker.role = Member.BOT
            speaker.save()

        server = source.server or "discord.com"
        #https://discordapp.com/channels/742145874070601729/742145874628706377/742413532678848523
        discord_convo_id = message.get('id')
        discord_convo_link = "%s/channels/%s/%s/%s" % (server, source.auth_id, channel.origin_id, discord_convo_id)
        convo_text = message.get('content')

        participants.add(speaker)
        for tagged_user in message.get('mentions', []):
            member = self.make_member(tagged_user.get('id'), channel=channel, detail=tagged_user.get('username'), email_address=tagged_user.get('email'), tstamp=tstamp, speaker=False, name=tagged_user.get('username'))
            participants.add(member)
            convo_text = convo_text.replace("<@!%s>"%tagged_user.get('id'), "@%s"%tagged_user.get('username'))
            if (tagged_user.get('bot', False) or tagged_user.get('system', False))and member.role != Member.BOT:
                member.role = Member.BOT
                member.save()

        convo = self.make_conversation(origin_id=discord_convo_id, channel=channel, speaker=speaker, content=convo_text, tstamp=tstamp, location=discord_convo_link)
        self.add_participants(convo, participants)
        return convo