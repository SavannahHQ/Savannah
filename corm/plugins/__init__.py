import datetime
import re
import subprocess
import requests
from importlib import import_module
from time import sleep
from corm.models import Member, MemberWatch, Contact, Conversation, Contribution
from corm.connectors import ConnectionManager
from django.conf import settings
from django.shortcuts import reverse
from django.contrib.contenttypes.models import ContentType
from notifications.signals import notify
from notifications.models import Notification

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

    def search_channels(self, source, text):
        matching = []
        for channel in self.get_channels(source):
            if text in channel['name']:
                matching.append(channel)
        return matching
                
    def get_channels(self, source):
        return []
        
class PluginImporter:

    def __init__(self, source):
        self.source = source
        self.community = source.community
        self.verbosity = 0
        self.full_import = False
        self._member_cache = dict()
        self.API_HEADERS = dict()
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
        self.TAGGED_USER_MATCHER = re.compile('\@([a-zA-Z0-9]+)')
        self.API_BACKOFF_ATTEMPTS = 5
        self.API_BACKOFF_SECONDS = 10


    def make_member(self, origin_id, detail, tstamp=None, channel=None, email_address=None, avatar_url=None, name=None, speaker=False, replace_first_seen=False):
        save_member = False
        if origin_id in self._member_cache:
            member = self._member_cache[origin_id]
        else:
            if name is None:
                name = detail
            contact_matches = Contact.objects.filter(origin_id=origin_id, source=self.source)
            if contact_matches.count() == 0:
                first_seen = tstamp
                if first_seen is None:
                    first_seen = datetime.datetime.utcnow()
                member = Member.objects.create(community=self.community, name=name, first_seen=first_seen, last_seen=None)
                contact, created = Contact.objects.get_or_create(origin_id=origin_id, source=self.source, defaults={'member':member, 'detail':detail})
                if created:
                    self.update_identity(contact)
            else:
                matched_contact = contact_matches[0]
                if detail:
                    matched_contact.detail = detail
                if name and not matched_contact.name or matched_contact.name == matched_contact.detail:
                    matched_contact.name = name
                if email_address and not matched_contact.email_address:
                    matched_contact.email_address = email_address
                if avatar_url and not matched_contact.avatar_url:
                    matched_contact.avatar_url = avatar_url
                matched_contact.save()
                member = matched_contact.member

                if member.name == matched_contact.detail and matched_contact.name is not None:
                    member.name = matched_contact.name
                    save_member = True
                if member.email_address is None:
                    member.email_address = matched_contact.email_address
                    save_member = True
                if member.avatar_url is None:
                    member.avatar_url = matched_contact.avatar_url
                    save_member = True

            self._member_cache[origin_id] = member
        if member.first_seen == replace_first_seen and tstamp is not None:
            member.first_seen = tstamp
            save_member = True

        if speaker and tstamp is not None:
            if member.first_seen is None or tstamp < member.first_seen:
                member.first_seen = tstamp
                save_member = True
            if member.last_seen is None or tstamp > member.last_seen:
                member.last_seen = tstamp
                save_member = True
        if save_member:
            member.save()

        if speaker and tstamp is not None:
            for watch in MemberWatch.objects.filter(member=member, start__lte=tstamp):
                if watch.last_seen is None or tstamp > watch.last_seen:
                    watch.last_seen = tstamp
                    watch.last_channel = channel
                    watch.save()
                has_recent_notification = Notification.objects.filter(recipient=watch.manager, actor_object_id=member.id, actor_content_type=ContentType.objects.get_for_model(member), verb="has been active in", timestamp__gte=tstamp - datetime.timedelta(hours=1)).count()
                if not has_recent_notification:
                    notify.send(member, 
                        recipient=watch.manager, 
                        verb="has been active in",
                        target=member.community,
                        level='error',
                        timestamp=tstamp,
                        icon_name="fas fa-eye",
                        link=reverse('member_profile', kwargs={'member_id':member.id}),
                        source=self.source.id,
                    )
        return member

    def make_conversation(self, origin_id, channel, speaker, content=None, tstamp=None, location=None, thread=None, dedup=False):
        if dedup:
            try:
                return Conversation.objects.filter(origin_id=origin_id, channel__source__community=self.community)[0]
            except:
                pass
        convo, created = Conversation.objects.update_or_create(origin_id=origin_id, channel=channel, defaults={'speaker':speaker, 'content':content, 'timestamp':tstamp, 'location':location, 'thread_start':thread})
        if content is not None:
            tagged_users = self.get_tagged_users(content)
            for tagged in tagged_users:
                if tagged in self._member_cache:
                    convo.participants.add(self._member_cache[tagged_users])
        return convo

    def api_request(self, url, headers):
        if self.verbosity:
            print("API Call: %s" % url)
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
        if len(self.source.server) > 0 and self.source.server[-1] == '/' and path[0] == '/':
            path = path[1:]
        return self.api_request(self.source.server+path, headers=self.API_HEADERS)

    def strftime(self, dtime):
        return dtime.strftime(self.TIMESTAMP_FORMAT)

    def strptime(self, dtimestamp):
        return datetime.datetime.strptime(dtimestamp, self.TIMESTAMP_FORMAT)

    def get_user_tags(self, content):
        return set(self.TAGGED_USER_MATCHER.findall(content))

    def get_tagged_users(self, content):
        return []

    def get_channels(self):
        channels = self.source.channel_set.filter(origin_id__isnull=False, source__auth_secret__isnull=False).order_by('last_import')
        return channels

    def run(self):
        failures = list()
        for channel in self.get_channels():
            if not channel.enabled:
                continue
            try:
                self.import_channel(channel)
                if self.verbosity > 2:
                    print("Completed import of %s" % channel.name)
                if channel.first_import is None:
                    channel.first_import = datetime.datetime.utcnow()
                    recipients = self.source.community.managers or self.source.community.owner
                    notify.send(channel, 
                        recipient=recipients, 
                        verb="has been imported into",
                        target=self.community,
                        level='success',
                        icon_name="fas fa-file-import",
                        link=reverse('channels', kwargs={'source_id':self.source.id, 'community_id':self.source.community.id})
                    )
                channel.last_import = datetime.datetime.utcnow()
                channel.import_failed_attempts = 0
                channel.import_failed_message = None
                channel.save()
            except Exception as e:
                    channel.import_failed_attempts += 1
                    channel.import_failed_message = str(e)
                    if channel.import_failed_attempts >= settings.MAX_CHANNEL_IMPORT_FAILURES:
                        channel.enabled = False
                    channel.save()
                    failures.append(channel.name)
                    recipients = self.source.community.managers or self.source.community.owner
                    notify.send(channel, 
                        recipient=recipients, 
                        verb="failed to import into",
                        target=self.community,
                        level='error',
                        icon_name="fas fa-file-import",
                        link=reverse('channels', kwargs={'source_id':self.source.id, 'community_id':self.source.community.id}),
                        error=str(e)
                    )
                    if self.verbosity:
                        print("Failed to import %s: %s" %(channel.name, e))
        self.source.last_import = datetime.datetime.utcnow()
        if self.source.first_import is None:
            self.source.first_import = datetime.datetime.utcnow()
        if len(failures) > 0:
            self.source.import_failed_attempts += 1
            if self.source.import_failed_attempts >= settings.MAX_SOURCE_IMPORT_FAILURES:
                self.source.enabled = False
            if len(failures) == 1:
                self.source.import_failed_message = "Failed to import channel: %s" % failures[0]
            else:
                self.source.import_failed_message = "Failed to import %s channels" % len(failures)
        else:
            self.source.import_failed_attempts = 0
            self.source.import_failed_message = None

        self.source.save()

    def import_channel(self, channel):
        raise NotImplementedError

    def update_identity(self, identity):
        pass