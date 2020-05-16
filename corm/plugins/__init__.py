import datetime
import re
import subprocess
import requests
from importlib import import_module
from time import sleep
from corm.models import Member, Contact, Conversation, Contribution
from corm.connectors import ConnectionManager
from django.conf import settings
from django.shortcuts import reverse
from notifications.signals import notify

def install_plugins():
    for plugin in settings.CORM_PLUGINS:
        plugin_module, plugin_name = plugin.rsplit(".", maxsplit=1)
        module = import_module(plugin_module)
        plugin_class = getattr(module, plugin_name, None)
        if plugin_class is not None:
            print("Loaded plugin: %s" % plugin)
            ConnectionManager.add_plugin(plugin_module, plugin_class())
        else:
            print("Failed to load plugin: %s" % plugin)

class BasePlugin:

    def __init__(self):
        pass

    def get_identity_url(self, contact):
        return None

    def get_source_type_name(self):
        return self.__class__.__name__

    def get_import_command_name(self):
        return None

    def get_source_importer(self, source):
        raise NotImplementedError

    def get_channels(self, source):
        return []
        
class PluginImporter:

    def __init__(self, source):
        self.source = source
        self.community = source.community
        self._member_cache = dict()
        self.API_HEADERS = dict()
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
        self.TAGGED_USER_MATCHER = re.compile('\@([a-zA-Z0-9]+)')
        self.API_BACKOFF_ATTEMPTS = 5
        self.API_BACKOFF_SECONDS = 10


    def make_member(self, origin_id, detail, tstamp=None, email_address=None, avatar_url=None, name=None):
        if origin_id in self._member_cache:
            member = self._member_cache[origin_id]
            if tstamp is not None and (member.last_seen is None or tstamp > member.last_seen):
                member.last_seen = tstamp
                member.save()
        else:
            if name is None:
                name = detail
            contact_matches = Contact.objects.filter(origin_id=origin_id, source=self.source)
            if contact_matches.count() == 0:
                member = Member.objects.create(community=self.community, name=name, first_seen=tstamp, last_seen=tstamp)
                contact, created = Contact.objects.get_or_create(origin_id=origin_id, source=self.source, defaults={'member':member, 'detail':detail})
            else:
                member = contact_matches[0].member
            self._member_cache[origin_id] = member
        return member

    def make_conversation(self, origin_id, channel, speaker, content=None, tstamp=None, location=None, thread=None):
        convo, created = Conversation.objects.update_or_create(origin_id=origin_id, defaults={'channel':channel, 'speaker':speaker, 'content':content, 'timestamp':tstamp, 'location':location, 'thread_start':thread})
        if content is not None:
            tagged_users = self.get_tagged_users(content)
            for tagged in tagged_users:
                if tagged in self._member_cache:
                    convo.participants.add(self._member_cache[tagged_users])
        return convo

    def api_request(self, url, headers):
        retries = self.API_BACKOFF_ATTEMPTS
        backoff_time = 0
        resp = requests.get(url, headers=headers)
        while resp.status_code == 429 and retries > 0:
            retries -= 1
            if settings.DEBUG:
                print("API backoff, %s retries remaining" % retries)
            backoff_time += self.API_BACKOFF_SECONDS
            sleep(backoff_time)
            resp = requests.get(url, headers=headers)
        return resp

    def api_call(self, path):
        if settings.DEBUG:
            print("API Call: %s" % path)
        return self.api_request(self.source.server+path, headers=self.API_HEADERS)

    def strftime(self, dtime):
        return dtime.strftime(self.TIMESTAMP_FORMAT)

    def strptime(self, dtimestamp):
        return datetime.datetime.strptime(dtimestamp, self.TIMESTAMP_FORMAT)

    def get_tagged_users(self, content):
        return []

    def get_channels(self):
        channels = self.source.channel_set.filter(origin_id__isnull=False, source__auth_secret__isnull=False).order_by('last_import')
        return channels

    def run(self):
        for channel in self.get_channels():
            self.import_channel(channel)
            if channel.last_import is None:
                recipients = self.source.community.managers or self.source.community.owner
                notify.send(channel, 
                    recipient=recipients, 
                    verb="has been imported for the first time.",
                    level='success',
                    icon_name="fas fa-file-import",
                    link=reverse('channels', kwargs={'source_id':self.source.id, 'community_id':self.source.community.id})
                )
            channel.last_import = datetime.datetime.utcnow()
            channel.save()
        self.source.last_import = datetime.datetime.utcnow()
        self.source.save()

    def import_channel(self, channel):
        raise NotImplementedError