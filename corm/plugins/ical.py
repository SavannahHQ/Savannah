import datetime
import re
import requests
from icalendar import Calendar
import io
import pytz

from django.contrib import messages
from django import forms
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.conf import settings

from corm.plugins import BasePlugin, PluginImporter
from corm.models import Community, Source, ContributionType, Contribution, EventAttendee
from frontendv2.views import SavannahView

class iCalForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['name', 'server']
        labels = {
            'server': 'iCal URL',
        }
    def __init__(self, *args, **kwargs):
        super(iCalForm, self).__init__(*args, **kwargs)
        self.fields['server'].required = True

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        view = SourceAdd(request, community_id=request.session['community'])
        if not view.community.management.can_add_source():
            messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
            return redirect('sources', community_id=view.community.id)

        new_source = Source(community=view.community, connector="corm.plugins.ical", icon_name="fas fa-calendar-alt")
        if request.method == "POST":
            form = iCalForm(data=request.POST, instance=new_source)
            if form.is_valid():
                # TODO: attempt API call to validate
                source = form.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        form = iCalForm(instance=new_source)
        context = view.context
        context.update({
            'source_form': form,
            'source_plugin': 'Calendar',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, 'savannahv2/source_add.html', context)

urlpatterns = [
    path('auth', SourceAdd.as_view, name='ical_auth'),
]

class iCalPlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_icon_name(self):
        return 'fas fa-calendar-alt'

    def get_source_type_name(self):
        return "iCal"

    def get_import_command_name(self):
        return "ical"

    def get_auth_url(self):
        return reverse('ical_auth')

    def get_source_importer(self, source):
        return iCalImporter(source)

    def get_channels(self, source):
        channels = []

        resp = requests.get(source.server)   
        if resp.status_code == 200:
            data = resp.text
            print(data[:500])
            try:
                ical = Calendar.from_ical(data)
                name = ical.get('X-WR-CALNAME', 'Default Calendar')
                topic = ical.get('X-WR-CALDESC', ical.get('PRODID', '-//Unknown//Unknown//EN'))
                channels = [{
                    'id': source.server,
                    'name': name,
                    'topic': topic,
                    'count': 0
                }]
            except:
                raise Exception("Could not read ical file at %s" % source.server)
        else:
            print("Request failed: %s" % resp.content)
            raise Exception("Request failed: %s" % resp.status_code)
        return channels

class iCalImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%Y%m%dT%H:%M:%Sz'
        self.TIMESTAMP_FORMAT_WITH_OFFSET = '%Y%m%dT%H:%M:%S%z'
        self.HOST_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Hosted")
        self.SPEAKER_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Speaker")


    def strptime(self, dtimestamp):
        try:
            return datetime.datetime.strptime(dtimestamp, self.TIMESTAMP_FORMAT)
        except:
            return datetime.datetime.strptime(dtimestamp, self.TIMESTAMP_FORMAT_WITH_OFFSET)

    def member_details(self, address):
        print('ADDRESS: %s' % address)
        member_email = address.to_ical().decode('utf-8')
        if member_email[:7] == 'mailto:':
            member_email = member_email[7:]
        if 'CN' in address.params:
            member_detail = address.params['CN']
        else:
            member_detail = member_email
        if member_detail == member_email:
            member_detail = member_email.split('@')[0]
        return (member_email, member_detail)

    def get_channels(self):
        channels = self.source.channel_set.filter(origin_id__isnull=False).order_by('last_import')
        return channels

    def import_channel(self, channel, from_date, full_import=False):
      source = channel.source
      community = source.community

      resp = requests.get(channel.origin_id)
      if resp.status_code == 200:
          ical = Calendar.from_ical(resp.text)
          for comp in ical.walk():
              if comp.name == 'VEVENT':
                self.import_event(comp, channel, source, community)

    def import_event(self, ical_event, channel, source, community):
        print(ical_event)

        event_id = ical_event['UID']
        title = ical_event['SUMMARY']
        description = ical_event['DESCRIPTION']
        location = ical_event.get('URL', None)

        start_timestamp = ical_event['DTSTART'].dt
        end_timestamp = ical_event['DTEND'].dt
        if not settings.USE_TZ:
            try:
                start_timestamp = ical_event['DTSTART'].dt.replace(tzinfo=None)
                end_timestamp = ical_event['DTEND'].dt.replace(tzinfo=None)
            except:
                pass # It's possible these are Date and not Datetime
        status = ical_event.get('STATUS', 'CONFIRMED')

        event = self.make_event(event_id, channel, title, description, start=start_timestamp, end=end_timestamp, location=location)
        if channel.tag is not None and event.tag is None:
            event.tag = channel.tag
            event.save()

        organizer = None
        members = []
        if 'ORGANIZER' in ical_event:
            organizer = ical_event.get('ORGANIZER')
            member_email, member_detail = self.member_details(organizer)
            print('ORGANIZER: %s <%s>' % (member_detail, member_email))
            organizer = self.make_member(member_email, member_detail, channel=channel)
            members.append(organizer)
        if 'ATTENDEE' in ical_event:
            if isinstance(ical_event['ATTENDEE'], list):
                for attendee in ical_event['ATTENDEE']:
                    member_email, member_detail = self.member_details(attendee)
                    print('ATTENDEE: %s' % member_email)
                    member = self.make_member(member_email, member_detail, channel=channel)
                    members.append(member)
            else: 
                attendee = ical_event['ATTENDEE']
                member_email, member_detail = self.member_details(attendee)
                print('ATTENDEE: %s' % member_email)
                member = self.make_member(member_email, member_detail, channel=channel)
                members.append(member)
        self.add_event_attendees(event, members, make_connections=True)

        if organizer:
            self.add_event_attendee(event, organizer, EventAttendee.HOST)
            contrib, contrib_created = Contribution.objects.get_or_create(
                community=self.community,
                channel=channel,
                author=organizer,
                contribution_type=self.HOST_CONTRIBUTION,
                timestamp=event.start_timestamp,
                defaults={
                    'location': event.location,
                    'title': 'Hosted %s' % event.title,
                }
            )
