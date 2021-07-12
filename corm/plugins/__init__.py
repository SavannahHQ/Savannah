import datetime
import re
import subprocess
import requests
from importlib import import_module
from time import sleep
from corm.models import Member, MemberWatch, Contact, Conversation, Contribution, Participant, ManagerProfile, Event, EventAttendee
from corm.connectors import ConnectionManager
from corm.email import EmailMessage
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

class MemberWatchEmail(EmailMessage):
    def __init__(self, watch):
        super(MemberWatchEmail, self).__init__(watch.manager, watch.member.community)
        self.subject = "Watched member %s has been active" % watch.member.name
        self.category = "member_watch"
        self.context.update({
            'watch': watch,
        })

        self.text_body = "emails/watched_member_seen.txt"
        self.html_body = "emails/watched_member_seen.html"

class BasePlugin:

    def __init__(self):
        pass

    def get_icon_name(self):
        return 'fas fa-cogs'

    def get_auth_url(self):
        return ''

    def get_identity_url(self, contact):
        return None

    def get_connector(self):
        return self.__class__.__module__

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
        self.debug = False
        self._first_import = False
        self._full_import = False
        self._member_cache = dict()
        self.API_HEADERS = dict()
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
        self.TAGGED_USER_MATCHER = re.compile('\@([a-zA-Z0-9]+)')
        self.API_BACKOFF_ATTEMPTS = getattr(settings, 'API_BACKOFF_ATTEMPTS', 5)
        self.API_BACKOFF_SECONDS = getattr(settings, 'API_BACKOFF_SECONDS', 10)

    def get_full_import(self):
        return self._full_import or self._first_import

    def set_full_import(self, val=None):
        self._full_import = val
    full_import = property(get_full_import, set_full_import)

    def get_first_import(self):
        return self._first_import

    def set_first_import(self, val=None):
        self._first_import = val
    first_import = property(get_first_import, set_first_import)

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
                contact = Contact.objects.create(origin_id=origin_id, source=self.source, member=member, detail=detail, name=name, email_address=email_address, avatar_url=avatar_url)
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
                    try:
                        profile = ManagerProfile.objects.get(user=watch.manager, community=watch.member.community)
                    except ManagerProfile.DoesNotExist:
                        continue
                    except Exception as e:
                        print(e)
                        continue

                    if profile and profile.send_notifications == True:
                        email = MemberWatchEmail(watch)
                        email.send(profile.email)
        return member

    def make_conversation(self, origin_id, channel, speaker, content=None, tstamp=None, location=None, thread=None, contribution=None, dedup=False):
        if dedup:
            try:
                return Conversation.objects.filter(origin_id=origin_id, channel__source__community=self.community)[0]
            except:
                pass

        convo, created = Conversation.objects.update_or_create(origin_id=origin_id, channel=channel, defaults={'timestamp':tstamp, 'location':location, 'thread_start':thread, 'contribution':contribution})
        if content is not None and (convo.content is None or len(convo.content) < len(content)):
            convo.content = content
        if speaker is not None:
            convo.speaker = speaker
        convo.save()
        convo.update_activity()

        if content is not None:
            tagged_users = self.get_tagged_users(content)
            for tagged in tagged_users:
                if tagged in self._member_cache:
                    self.make_participant(convo, self._member_cache[tagged_users])
        return convo

    def add_participants(self, conversation, members, make_connections=True):
        for member in members:
            try:
                participant, created = Participant.objects.get_or_create(
                    community=self.community, 
                    conversation=conversation,
                    member=member,
                    defaults={
                        'initiator': conversation.speaker,
                        'timestamp':conversation.timestamp,
                    }
                )
                if created and make_connections:
                    for to_member in members:
                        if member.id != to_member.id:
                            member.add_connection(to_member, conversation.timestamp)
            except:
                pass

    def make_participant(self, conversation, member):
        try:
            participant, created = Participant.objects.get_or_create(
                community=self.community, 
                conversation=conversation,
                member=member,
                defaults={
                    'initiator': conversation.speaker,
                    'timestamp':conversation.timestamp,
                }
            )
            if created:
                if conversation.speaker.id != member.id:
                    member.add_connection(conversation.speaker, conversation.timestamp)
        except:
            pass

    def make_event(self, origin_id, channel, title, description, start, end, location=None, dedup=False):
        if dedup:
            try:
                return Event.objects.filter(origin_id=origin_id, channel__source__community=self.community)[0]
            except:
                pass
        event, created = Event.objects.update_or_create(origin_id=origin_id, community=self.community, source=self.source, defaults={'channel':channel, 'title':title, 'description':description, 'start_timestamp':start, 'end_timestamp':end, 'location':location})
        return event

    def add_event_attendees(self, event, members, make_connections=False):
        for member in members:
            try:
                attendee, created = EventAttendee.objects.get_or_create(
                    community=self.community, 
                    event=event,
                    member=member,
                    timestamp=event.start_timestamp
                )
                attendee.update_activity()
                tstamp = event.start_timestamp
                save_member = False
                if tstamp is not None:
                    if member.first_seen is None or tstamp < member.first_seen:
                        member.first_seen = tstamp
                        save_member = True
                    if member.last_seen is None or tstamp > member.last_seen:
                        member.last_seen = tstamp
                        save_member = True
                if save_member:
                    member.save()

                if created and make_connections:
                    for to_member in members:
                        if member.id != to_member.id:
                            member.add_connection(to_member, event.start_timestamp)
            except:
                pass

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

    def run(self, new_only=False):
        failures = list()
        channels = self.get_channels()
        channels = channels.filter(enabled=True)
        if new_only:
            channels = channels.filter(first_import__isnull=True)
        if channels.count() == 0:
            raise Exception("No channels to import")

        for channel in channels:
            if self.verbosity >= 2:
                print("Importing channel: %s" % channel.name)
            full_import = self.full_import
            first_import = self.first_import
            try:
                if channel.first_import is None:
                    channel.first_import = datetime.datetime.utcnow()
                    first_import = True
                    channel.save()

                if channel.last_import and not self.full_import:
                    from_date = channel.last_import
                else:
                    from_date = datetime.datetime.utcnow() - datetime.timedelta(days=settings.MAX_IMPORT_HISTORY_DAYS)
                    # Because we're going a full import, set the last_imported to now to avoid the next run
                    # also trying to do a full import if this one hasn't finished yet.
                    full_import = True
                    channel.last_import = datetime.datetime.utcnow()
                    channel.save()
                if self.verbosity >= 2:
                    print("From %s since %s" % (channel.name, from_date))

                self.import_channel(channel, from_date, full_import)

                if self.verbosity > 2:
                    print("Completed import of %s" % channel.name)
                if first_import:
                    recipients = self.source.community.managers or self.source.community.owner
                    notify.send(channel, 
                        recipient=recipients, 
                        verb="has been imported into",
                        target=self.community,
                        level='success',
                        icon_name="fas fa-file-import",
                        link=reverse('channels', kwargs={'source_id':self.source.id, 'community_id':self.source.community.id})
                    )
                if channel.oldest_import is None or from_date < channel.oldest_import:
                    channel.oldest_import = from_date
                channel.last_import = datetime.datetime.utcnow()
                channel.import_failed_attempts = 0
                channel.import_failed_message = None
                channel.save()
            except Exception as e:
                if first_import:
                    channel.first_import = None
                    channel.oldest_import = None
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
                if self.debug:
                    # Drop into PDB to debug the import exception
                    import pdb; pdb.post_mortem()
            if self.full_import:
                sleep(5)
        self.source.last_import = datetime.datetime.utcnow()
        if self.source.first_import is None:
            self.source.first_import = self.source.last_import
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