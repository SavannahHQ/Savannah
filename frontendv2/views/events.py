import operator
from functools import reduce
import datetime
import csv
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, Min
from django.db.models.functions import Trunc, Lower

from django.contrib import messages
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import PieChart, ChartColors
from frontendv2 import colors

class EventProfile(SavannahView):
    def __init__(self, request, event_id):
        self.event = get_object_or_404(Event, id=event_id)
        super().__init__(request, self.event.community.id)
        self.active_tab = "events"
        self.timespan=366

        self.RESULTS_PER_PAGE = 25
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'event_search' in request.GET:
            self.event_search = request.GET.get('event_search', "").lower()
        else:
            self.event_search = None
        self.result_count = 0

    @property
    def attendee_count(self):
        return EventAttendee.objects.filter(event=self.event).count()

    @property
    def all_attendees(self):
        attendees = EventAttendee.objects.filter(event=self.event).select_related('member')
        if self.event_search:
            attendees = attendees.filter(member__name__icontains=self.event_search)

        attendees = attendees.annotate(events_count=Count('member__event_attendance'))
        self.result_count = attendees.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return attendees[start:start+self.RESULTS_PER_PAGE]

    @property
    def page_start(self):
        return ((self.page-1) * self.RESULTS_PER_PAGE) + 1

    @property
    def page_end(self):
        end = ((self.page-1) * self.RESULTS_PER_PAGE) + self.RESULTS_PER_PAGE
        if end > self.result_count:
            return self.result_count
        else:
            return end

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        return pages

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        offset=1
        if self.page > 5:
            offset = self.page - 5
        if offset + 9 > pages:
            offset = pages - 9
        if offset < 1:
            offset = 1
        return [page+offset for page in range(min(10, pages))]

    @login_required
    def as_csv(request, event_id):
        view = EventProfile(request, event_id)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="attendees.csv"'
        writer = csv.DictWriter(response, fieldnames=['Event', 'Member', 'Email', 'Attended', 'Role'])
        writer.writeheader()
        for attendee in EventAttendee.objects.filter(event=view.event).select_related('member'):
            writer.writerow({
                'Event': attendee.event.title, 
                'Member':attendee.member, 
                'Email':attendee.member.email_address, 
                'Attended': attendee.timestamp,
                'Role':EventAttendee.ROLE_NAME[attendee.role], 
            })
        return response

    @login_required
    def as_view(request, event_id):
        view = EventProfile(request, event_id)
        if request.method == 'POST':
            if 'delete_attendee' in request.POST:
                attendee = get_object_or_404(EventAttendee, id=request.POST.get('delete_attendee'))
                context = view.context
                context.update({
                    'object_type':"Attendee", 
                    'object_name': attendee.member.name, 
                    'object_id': attendee.id,
                    'warning_msg': "This will remove the record of this Member attending this Event.",
                })
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                attendee = get_object_or_404(EventAttendee, id=request.POST.get('object_id'))
                attendee_name = attendee.member.name
                try:
                    contrib = Contribution.objects.get(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                    ).delete()
                except Contribution.DoesNotExist:
                    pass # There was no Contribution
                except Exception as e:
                    raise e
                member = attendee.member
                attendee.delete()
                try:
                    member.last_seen = member.activity.order_by('-timestamp')[0].timestamp
                    member.save()
                except Exception as e:
                    if member.activity.count() == 0:
                        member.last_seen = member.first_seen

                messages.success(request, "Deleted attendee: <b>%s</b>" % attendee_name)

                return redirect('event', event_id=event_id)

        return render(request, "savannahv2/event.html", view.context)

from django.http import JsonResponse
@login_required
def tag_event(request, community_id):
    community = get_object_or_404(Community, id=community_id)
    if request.method == "POST":
        try:
            event_id = request.POST.get('event_id')
            event = Event.objects.get(community=community, id=event_id)
            tag_id = request.POST.get('tag_select')
            try:
                event.tag = Tag.objects.get(id=tag_id, community=community_id)
                event.save()
            except:
                messages.error(request, "Unkown tag")
                raise RuntimeError("Known Tag")
            return JsonResponse({'success': True, 'errors':None})
        except Exception as e:
            return JsonResponse({'success':False, 'errors':str(e)})
    return JsonResponse({'success':False, 'errors':'Only POST method supported'})

class EventAttendeeForm(forms.ModelForm):
    class Meta:
        model = EventAttendee
        fields = ['member', 'role', 'timestamp']
        widgets = {
            'timestamp': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }

    def limit(self):
        if self.instance and hasattr(self.instance, 'member'):
            self.fields['member'].widget.choices = [(self.instance.member.id, self.instance.member.name)]
        else:
            self.fields['member'].widget.choices = []


class AddAttendee(SavannahView):
    def __init__(self, request, event_id):
        self.event = get_object_or_404(Event, id=event_id)
        super().__init__(request, self.event.community.id)
        self.edit_attendee = EventAttendee(community=self.community, event=self.event, timestamp=self.event.start_timestamp)
        if request.GET.get('attendee'):
            try:
                self.edit_attendee = EventAttendee.objects.get(community=self.community, event=self.event, id=request.GET.get('attendee'))
            except:
                pass
        if request.GET.get('role') == 'host':
            self.edit_attendee.role = EventAttendee.HOST
        if request.GET.get('role') == 'speaker':
            self.edit_attendee.role = EventAttendee.SPEAKER
        if request.GET.get('role') == 'staff':
            self.edit_attendee.role = EventAttendee.STAFF
        self.active_tab = "events"

    @property
    def form(self):
        if self.request.method == 'POST':
            form = EventAttendeeForm(instance=self.edit_attendee, data=self.request.POST)
        else:
            form = EventAttendeeForm(instance=self.edit_attendee)
        form.limit()
        return form

    @login_required
    def as_view(request, event_id):
        view = AddAttendee(request, event_id)
        if request.method == "POST" and view.form.is_valid():
            new_attendee = view.form.save(commit=False)
            source = None
            if view.event.channel is not None:
                source = view.event.channel.source
            hosted, created = ContributionType.objects.get_or_create(community=view.event.community, source=source, name="Hosted")
            speaker, created = ContributionType.objects.get_or_create(community=view.event.community, source=source, name="Speaker")
            staff, created = ContributionType.objects.get_or_create(community=view.event.community, source=source, name="Staff")

            attendee, attendee_created = EventAttendee.objects.update_or_create(community=view.community, event=view.event, member=new_attendee.member, defaults={'role': new_attendee.role, 'timestamp': new_attendee.timestamp})
            if attendee.member.last_seen is None:
                attendee.member.first_seen = attendee.timestamp
                attendee.member.last_seen = attendee.timestamp
                attendee.member.save()
            elif attendee.timestamp > attendee.member.last_seen:
                attendee.member.last_seen = attendee.timestamp
                attendee.member.save()
            attendee.update_activity()
            if attendee_created:
                if attendee.role == EventAttendee.HOST:
                    contrib, contrib_created = Contribution.objects.get_or_create(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                        defaults={
                            'location': view.event.location,
                            'title': 'Hosted %s' % view.event.title,
                            'contribution_type': hosted,
                            'timestamp': attendee.timestamp
                        }

                    )
                    contrib.update_activity(attendee.activity)
                    messages.success(request, "<b>%s</b> made a host of this event" % attendee.member.name)
                elif attendee.role == EventAttendee.SPEAKER:
                    contrib, contrib_created = Contribution.objects.get_or_create(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                        defaults={
                            'location': view.event.location,
                            'title': 'Speaker at %s' % view.event.title,
                            'contribution_type': speaker,
                            'timestamp': attendee.timestamp
                        }
                    )
                    contrib.update_activity(attendee.activity)
                    messages.success(request, "<b>%s</b> made a speaker at this event" % attendee.member.name)
                elif attendee.role == EventAttendee.STAFF:
                    contrib, contrib_created = Contribution.objects.get_or_create(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                        defaults={
                            'location': view.event.location,
                            'title': 'Staff at %s' % view.event.title,
                            'contribution_type': staff,
                            'timestamp': attendee.timestamp
                        }
                    )
                    contrib.update_activity(attendee.activity)
                    messages.success(request, "<b>%s</b> made staff at this event" % attendee.member.name)
            else:
                if attendee.role == EventAttendee.GUEST:
                    try:
                        contrib = Contribution.objects.get(
                            community=view.event.community,
                            channel=view.event.channel,
                            author=attendee.member,
                            activity__event_attendance__event=view.event,
                        )
                        attendee.activity.contribution = None
                        attendee.activity.icon_name = 'fas fa-calendar-alt'
                        attendee.activity.short_description = 'Attended Event'
                        attendee.activity.save()
                        contrib.delete()
                    except Contribution.DoesNotExist:
                        pass # There was no Contribution
                    except Exception as e:
                        raise e
                elif attendee.role == EventAttendee.HOST:
                    contrib, contrib_created = Contribution.objects.update_or_create(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                        defaults={
                            'location': view.event.location,
                            'title': 'Hosted %s' % view.event.title,
                            'contribution_type': hosted,
                            'timestamp': attendee.timestamp
                        }
                    )
                    contrib.update_activity(attendee.activity)
                    messages.success(request, "<b>%s</b> made a host of this event" % attendee.member.name)
                elif attendee.role == EventAttendee.SPEAKER:
                    contrib, contrib_created = Contribution.objects.update_or_create(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                        defaults={
                            'location': view.event.location,
                            'title': 'Speaker at %s' % view.event.title,
                            'contribution_type': speaker,
                            'timestamp': attendee.timestamp
                        }
                    )
                    contrib.update_activity(attendee.activity)
                    messages.success(request, "<b>%s</b> made a speaker at this event" % attendee.member.name)
                elif attendee.role == EventAttendee.STAFF:
                    contrib, contrib_created = Contribution.objects.update_or_create(
                        community=view.event.community,
                        channel=view.event.channel,
                        author=attendee.member,
                        activity__event_attendance__event=view.event,
                        defaults={
                            'location': view.event.location,
                            'title': 'Staff at %s' % view.event.title,
                            'contribution_type': staff,
                            'timestamp': attendee.timestamp
                        }
                    )
                    contrib.update_activity(attendee.activity)
                    messages.success(request, "<b>%s</b> made staff at this event" % attendee.member.name)


            return redirect('event', event_id=view.event.id)

        return render(request, "savannahv2/attendee_add.html", view.context)

class Events(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "events"
        self.filter.update({
            'timespan': False,
            'custom_timespan': False,
            'member': False,
            'member_role': False,
            'member_tag': False,
            'member_company': False,
            'tag': False,
            'source': False,
            'conrib_type': False,
        })
        self.RESULTS_PER_PAGE = 25
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'event_search' in request.GET:
            self.event_search = request.GET.get('event_search', "").lower()
        else:
            self.event_search = None
        self.result_count = 0

        self._sourcesChart = None
        self._attendeeSourcesChart = None
        self._tagsChart = None

    def all_events(self):
        events = Event.objects.filter(community=self.community).annotate(attendee_count=Count('rsvp')).order_by('-start_timestamp')
        self.result_count = events.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return events[start:start+self.RESULTS_PER_PAGE]

    @property
    def page_start(self):
        return ((self.page-1) * self.RESULTS_PER_PAGE) + 1

    @property
    def page_end(self):
        end = ((self.page-1) * self.RESULTS_PER_PAGE) + self.RESULTS_PER_PAGE
        if end > self.result_count:
            return self.result_count
        else:
            return end

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        return pages

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        offset=1
        if self.page > 5:
            offset = self.page - 5
        if offset + 9 > pages:
            offset = pages - 9
        if offset < 1:
            offset = 1
        return [page+offset for page in range(min(10, pages))]

    def sourcesChart(self):
        if not self._sourcesChart:
            sources = Source.objects.filter(community=self.community)

            sources = sources.annotate(event_count=Count('event')).filter(event_count__gt=0).order_by('-event_count')

            self._sourcesChart = PieChart("sourcesChart", title="Events by Source", limit=5)
            for source in sources:
                self._sourcesChart.add("%s (%s)" % (source.name, ConnectionManager.display_name(source.connector)), source.event_count)
        self.charts.add(self._sourcesChart)
        return self._sourcesChart

    def attendeeSourcesChart(self):
        if not self._attendeeSourcesChart:
            sources = Source.objects.filter(community=self.community)

            sources = sources.annotate(attendee_count=Count('event__rsvp')).filter(attendee_count__gt=0).order_by('-attendee_count')

            self._attendeeSourcesChart = PieChart("attendeeSourcesChart", title="Attendees by Source", limit=5)
            for source in sources:
                self._attendeeSourcesChart.add("%s (%s)" % (source.name, ConnectionManager.display_name(source.connector)), source.attendee_count)
        self.charts.add(self._attendeeSourcesChart)
        return self._attendeeSourcesChart

    def tagsChart(self):
        if not self._tagsChart:
            tags = Tag.objects.filter(community=self.community)

            tags = tags.annotate(event_count=Count('event')).filter(event_count__gt=0).order_by('-event_count')

            self._tagsChart = PieChart("tagsChart", title="Events by Tag", limit=8)
            for tag in tags:
                self._tagsChart.add(tag.name, tag.event_count, tag.color)
        self.charts.add(self._tagsChart)
        return self._tagsChart

    @login_required
    def as_csv(request, community_id):
        view = Events(request, community_id)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="events.csv"'
        writer = csv.DictWriter(response, fieldnames=['Title', 'Start', 'End', 'Category', 'Attendee Count', 'Tag', 'Impact'])
        writer.writeheader()
        for event in Event.objects.filter(community=view.community).annotate(attendee_count=Count('rsvp')).order_by('-start_timestamp'):
            tag_name = ''
            channel_name = ''
            if event.tag:
                tag_name = event.tag.name
            if event.channel:
                channel_name = event.channel.name
            writer.writerow({
                'Title': event.title, 
                'Start':event.start_timestamp, 
                'End': event.end_timestamp,
                'Category':channel_name, 
                'Attendee Count':event.attendee_count,
                'Tag': tag_name,
                'Impact':event.impact
            })
        return response

    @login_required
    def as_view(request, community_id):
        view = Events(request, community_id)
        if request.method == 'POST':
            if 'delete_event' in request.POST:
                event = get_object_or_404(Event, id=request.POST.get('delete_event'))
                context = view.context
                context.update({
                    'object_type':"Event", 
                    'object_name': event.title, 
                    'object_id': event.id,
                    'warning_msg': "This will remove all attendance activity from this Event.",
                })
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                event = get_object_or_404(Event, id=request.POST.get('object_id'))
                event_name = event.title
                try:
                    Contribution.objects.filter(
                        community=event.community,
                        channel=event.channel,
                        activity__event_attendance__event=event,
                    ).delete()
                except:
                    pass
                    
                members = list(event.attendees)
                event.delete()
                for member in members:
                    try:
                        member.last_seen = member.activity.order_by('-timestamp')[0].timestamp
                        member.save()
                    except Exception as e:
                        if member.activity.count() == 0:
                            member.last_seen = member.first_seen

                messages.success(request, "Deleted event: <b>%s</b> and %s attendance records" % (event_name, len(members)))

                return redirect('events', community_id=community_id)

        return render(request, "savannahv2/events.html", view.context)


class EventEditForm(forms.ModelForm):
    channel = forms.CharField()
    class Meta:
        model = Event
        fields = ['title', 'description', 'location', 'channel', 'start_timestamp', 'end_timestamp']

        widgets = {
            'start_timestamp': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
            'end_timestamp': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }
    def __init__(self, *args, **kwargs):
        super(EventEditForm, self).__init__(*args, **kwargs)
        self.fields['start_timestamp'].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields['end_timestamp'].input_formats = ["%Y-%m-%dT%H:%M"]
        if self.initial.get('channel', None) is not None:
            self.initial['channel'] = self.instance.channel.name
        self.fields['channel'].label = "Category"
        self.fields['channel'].help_text = "Category for your events, such as Conference or Meetup."

    def clean_channel(self):
        channel_name = self.cleaned_data['channel']
        if not channel_name or channel_name == '':
            return None
        source = self.instance.source
        if source is None:
            source = self.instance.community.manual_source
        channel, created = Channel.objects.get_or_create(source=source, name=channel_name)
        return channel


class AddEvent(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.edit_event = Event(community=self.community, source=self.community.manual_source)
        self.active_tab = "events"

    @property
    def form(self):
        if self.request.method == 'POST':
            return EventEditForm(instance=self.edit_event, data=self.request.POST)
        else:
            return EventEditForm(instance=self.edit_event)

    @login_required
    def as_view(request, community_id):
        view = AddEvent(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            new_event = view.form.save()
            return redirect('event', event_id=new_event.id)

        return render(request, "savannahv2/event_add.html", view.context)

class EditEvent(SavannahView):
    def __init__(self, request, event_id):
        self.edit_event = get_object_or_404(Event, id=event_id)
        super().__init__(request, self.edit_event.community.id)
        self.active_tab = "events"

    @property
    def form(self):
        if self.request.method == 'POST':
            return EventEditForm(instance=self.edit_event, data=self.request.POST)
        else:
            return EventEditForm(instance=self.edit_event)

    @login_required
    def as_view(request, event_id):
        view = EditEvent(request, event_id)
        old_channel = view.edit_event.channel
        if request.method == "POST" and view.form.is_valid():
            edited_event = view.form.save()
            if old_channel != edited_event.channel and edited_event.channel is not None:
                for attendee in edited_event.rsvp.all():
                    attendee.activity.channel = edited_event.channel
                    attendee.activity.save()
                    if attendee.activity.contribution is not None:
                        attendee.activity.contribution.channel = edited_event.channel
                        attendee.activity.contribution.save()

            return redirect('event', event_id=edited_event.id)

        return render(request, "savannahv2/event_edit.html", view.context)

