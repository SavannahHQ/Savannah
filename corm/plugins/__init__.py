import datetime
import re
import subprocess
import requests
import urllib
from importlib import import_module
from time import sleep
from corm.models import Member, MemberWatch, Contact, Conversation, Contribution, Participant, ManagerProfile, Event, EventAttendee, Company, SourceGroup, CompanyDomains, Hyperlink
from corm.connectors import ConnectionManager
from corm.email import EmailMessage
from django.conf import settings
from django.shortcuts import reverse
from django.contrib.contenttypes.models import ContentType
from notifications.signals import notify
from notifications.models import Notification

# URL_MATCHER = re.compile(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s\|()<>]+|\(([^\s\|()<>]+|(\([^\s\|()<>]+\)))*\))+(?:\(([^\s\|()<>]+|(\([^\s\|()<>]+\)))*\)|[^\s\|`!()\[\]{};:'\".,<>?«»“”‘’]))")
URL_MATCHER = re.compile(r"(https?://[0-9a-zA-Z.-]+(:[0-9]+)?(/[^\s|()<>'\"]*)?)")

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
    def __init__(self, watch, convo=None):
        super(MemberWatchEmail, self).__init__(watch.manager, watch.member.community)
        self.subject = "Watched member %s has been active" % watch.member.name
        self.category = "member_watch"
        self.context.update({
            'watch': watch,
            'convo': convo,
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

    def get_company_url(self, group):
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
        
    def get_channel_add_warning(self, channel):
        return None

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

    @property
    def plugin(self):
        try:
            return ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
        except:
            return None

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
                last_seen = None
                if speaker and tstamp:
                    last_seen = tstamp
                member = Member.objects.create(community=self.community, name=name, email_address=email_address, avatar_url=avatar_url, first_seen=first_seen, last_seen=last_seen)
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
                self.update_identity(matched_contact)

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

        return member

    def make_conversation(self, origin_id, channel, speaker, content=None, tstamp=None, location=None, thread=None, contribution=None, dedup=False):
        if dedup:
            try:
                return Conversation.objects.filter(origin_id=origin_id, channel__source__community=self.community)[0]
            except:
                pass

        convo, created = Conversation.objects.update_or_create(origin_id=origin_id, channel=channel, defaults={'channel': channel, 'timestamp':tstamp, 'location':location, 'thread_start':thread, 'contribution':contribution})
        if content is not None and (convo.content is None or len(convo.content) < len(content)):
            convo.content = content
        if tstamp is not None and speaker is not None and (speaker.last_seen is None or  speaker.last_seen < tstamp):
            speaker.last_seen = tstamp
            speaker.save()
        if speaker is not None:
            convo.speaker = speaker
        convo.save()
        convo.update_activity()

        if content is not None:
            tagged_users = self.get_tagged_users(content)
            for tagged in tagged_users:
                self.add_participants(convo, tagged_users)
            for link in self.get_links(content):
                try:
                    url = urllib.parse.urlparse(link)
                    if not url.hostname or not url.scheme:
                        continue
                    if self.verbosity >= 3:
                        print(link)
                    # Clean hostname
                    host = url.hostname
                    host_parts = host.split('.')
                    if len(host_parts) > 2:
                        try:
                            int(host_parts[-3])
                            pass # host is an IP
                        except:
                            try:
                                int(host_parts[-3][0])
                                # 3-rd level subdomain starts with a number and is likely generated
                                host = '.'.join(host_parts[-2:])
                            except:
                                pass
                    if host[:4] == 'www.':
                        host = host[4:] # Ignore www subdomains
                    # Determine content type
                    ctype = None
                    if url.path is not None and url.path != '':
                        ext = url.path.split('.')[-1].lower()
                        if ext in ['html', 'htm']:
                            ctype = 'Webpage'
                        elif ext in ['png', 'jpg', 'jpeg', 'gif', 'svg'] or host in ['i.imgur.com', 'media.giphy.com', 'i.reddit.com']:
                            ctype = 'Image'
                        elif ext in ['zip', 'tar', 'gz', 'xz']:
                            ctype = 'Archive'
                        elif ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']:
                            ctype = 'Document'
                        elif ext in ['py', 'rs', 'go', 'cpp', 'php', 'rb', 'js', 'ts']:
                            ctype = 'Code'
                        elif ext in ['py', 'rs', 'go', 'cpp', 'php', 'rb', 'js', 'ts']:
                            ctype = 'Code'
                        elif host in ['youtube.com', 'youtu.be', 'vimeo.com', 'twitch.com', 'v.reddit.com']:
                            ctype = 'Video'
                        else:
                            ctype = 'Webpage'
                    hl, created = Hyperlink.objects.get_or_create(
                        community=self.community,
                        url=link,
                        defaults={
                            'host':host,
                            'path':url.path or '/',
                            'content_type': ctype,
                        }
                    )
                    convo.links.add(hl)
                except:
                    pass # Keep going even if capturing the hyperlink fails

        if speaker and tstamp is not None:
            for watch in MemberWatch.objects.filter(member=speaker, start__lte=tstamp):
                if watch.last_seen is None or tstamp > watch.last_seen:
                    watch.last_seen = tstamp
                    watch.last_channel = channel
                    watch.save()
                has_recent_notification = Notification.objects.filter(recipient=watch.manager, actor_object_id=speaker.id, actor_content_type=ContentType.objects.get_for_model(speaker), verb="has been active in", timestamp__gte=tstamp - datetime.timedelta(hours=1)).count()
                if not has_recent_notification:
                    notify.send(speaker, 
                        recipient=watch.manager, 
                        verb="has been active in",
                        target=speaker.community,
                        level='error',
                        timestamp=tstamp,
                        icon_name="fas fa-eye",
                        link=reverse('member_activity', kwargs={'member_id':speaker.id}),
                        source=self.source.id,
                    )
                    try:
                        profile = ManagerProfile.objects.get(user=watch.manager, community=self.source.community)
                    except ManagerProfile.DoesNotExist:
                        continue
                    except Exception as e:
                        print(e)
                        continue

                    if profile and profile.send_notifications == True:
                        email = MemberWatchEmail(watch, convo)
                        email.send(profile.email)
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
            except Exception as e:
                print(e)
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
        event, created = Event.objects.update_or_create(origin_id=origin_id, community=self.community, source=self.source, channel=channel, defaults={'title':title, 'description':description, 'start_timestamp':start, 'end_timestamp':end, 'location':location})
        return event

    def make_company(self, name, origin_id=None, domain=None, website=None, logo=None, dedup=False):
        company = None
        if origin_id:
            try:
                group = SourceGroup.objects.get(source=self.source, origin_id=origin_id)
                company = group.company
            except:
                pass # No matching group found, so we'll create it later
        if domain:
            try:
                cd = CompanyDomains.objects.get(company__community=self.source.community, domain=domain)
                company = cd.company
            except:
                pass # No matching domain found, so we'll create it later
        if not company:
            company, created = Company.objects.get_or_create(community=self.source.community, name=name, defaults={'website':website, 'icon_url':logo})
        if origin_id:
            SourceGroup.objects.get_or_create(source=self.source, origin_id=origin_id, defaults={'company':company, 'name':name})
        if domain:
            CompanyDomains.objects.get_or_create(company=company, domain=domain)

        return company

    def add_event_attendees(self, event, members, make_connections=False, role=EventAttendee.GUEST):
        for member in members:
            attendee = self.add_event_attendee(event, member, role)
            
            if make_connections:
                for to_member in members:
                    if member.id != to_member.id:
                        member.add_connection(to_member, event.start_timestamp)


    def add_event_attendee(self, event, member, role=EventAttendee.GUEST):
        try:
            attendee, created = EventAttendee.objects.get_or_create(
                community=self.community, 
                event=event,
                member=member,
                defaults={
                    'role': role,
                    'timestamp': event.start_timestamp
                }
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

            return attendee
        except:
            pass

    def api_request(self, url, headers={}, params={}, retries=None, timeout=None):
        if self.verbosity or settings.DEBUG:
            print("API Call: %s" % url)
        if retries is None:
            retries = self.API_BACKOFF_ATTEMPTS
        backoff_time = 0
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        while resp.status_code == 429 and retries > 0:
            retries -= 1
            if settings.DEBUG:
                print("API backoff, %s retries remaining" % retries)
            backoff_time += self.API_BACKOFF_SECONDS
            sleep(backoff_time)
            resp = requests.get(url, headers=headers, timeout=timeout)
        return resp

    def api_call(self, path, retries=None, timeout=None):
        if len(self.source.server) > 0 and self.source.server[-1] == '/' and path[0] == '/':
            path = path[1:]
        return self.api_request(self.source.server+path, headers=self.API_HEADERS, retries=retries, timeout=timeout)

    def strftime(self, dtime):
        return dtime.strftime(self.TIMESTAMP_FORMAT)

    def strptime(self, dtimestamp):
        tstamp = datetime.datetime.strptime(dtimestamp, self.TIMESTAMP_FORMAT)
        if not settings.USE_TZ:
            tstamp = tstamp.replace(tzinfo=None)
        return tstamp

    def get_user_tags(self, content):
        return set(self.TAGGED_USER_MATCHER.findall(content))

    def get_tagged_users(self, content):
        return []

    def get_links(self, content):
        return [x[0] for x in URL_MATCHER.findall(content)]

    def get_channels(self):
        channels = self.source.channel_set.filter(origin_id__isnull=False, source__auth_secret__isnull=False).order_by('last_import')
        return channels

    def pre_import(self, new_only=False, channels=None):
        pass
    
    def post_import(self, new_only=False, channels=None):
        pass
    
    def run(self, new_only=False, channels=None):
        failures = list()
        self.update_source()
        if channels is None:
            channels = self.get_channels()
            channels = channels.filter(enabled=True)
        if new_only:
            channels = channels.filter(first_import__isnull=True)
        if channels.count() == 0:
            raise Exception("No channels to import")

        self.pre_import(new_only, channels)
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
                channel.save()
                failures.append(channel.name)
                if self.verbosity:
                    print("Failed to import %s: %s" %(channel.name, e))
                if self.debug:
                    # Drop into PDB to debug the import exception
                    import pdb; pdb.post_mortem()
            if self.full_import:
                sleep(5)

        self.post_import(new_only, channels)

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

    def update_source(self):
        pass