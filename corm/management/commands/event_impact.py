# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.db.models import Count, Q
from django.shortcuts import reverse
from corm.models import Community, Member, Conversation, Event
from corm.models import pluralize

CONTEXT_TIMESPAN = datetime.timedelta(days=30)

class Command(BaseCommand):
    help = 'Calculate the impact of an event on conversations'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--event', dest='event_id', type=int)

    def handle(self, *args, **options):
        community_id = options.get('community_id')
        event_id = options.get('event_id')
        self.verbosity = options.get('verbosity')

        event = None
        if event_id:
            event = Event.objects.get(id=event_id)
            print("Calculating impact of %s" % event.title)
            try:
                self.calculate_event_impact(event)
            except Exception as e:
                print("Error calculating impact for %s:" % event.title)
                print(e)
            return
        elif community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            communities = [community]
        else:
            communities = Community.objects.filter(status=Community.ACTIVE)

        for community in communities:
            for event in Event.objects.filter(community=community).filter(Q(impact=0)|Q(start_timestamp__lte=datetime.datetime.utcnow(), start_timestamp__gt=datetime.datetime.utcnow() - (2 * CONTEXT_TIMESPAN))):
                try:
                    self.calculate_event_impact(event)
                except Exception as e:
                    print("Error calculating impact for %s:" % event.title)
                    print(e)

    def calculate_event_impact(self, event):
        community = event.community

        event_context = CONTEXT_TIMESPAN
        if event.start_timestamp > datetime.datetime.utcnow() - (2 * event_context):
            event_context = (datetime.datetime.utcnow() - event.start_timestamp)/2
        baseline_start = event.start_timestamp - (2 * event_context)
        baseline_end = event.start_timestamp - event_context
        impact_end = event.start_timestamp + event_context
        bonus_end = event.start_timestamp + (2 * event_context)

        conversations = Conversation.objects.filter(speaker__community=community)
        baseline_count = conversations.filter(timestamp__gte=baseline_start, timestamp__lt=baseline_end).count()
        previous_count = conversations.filter(timestamp__gte=baseline_end, timestamp__lt=event.start_timestamp).count()
        new_count = conversations.filter(timestamp__gte=event.start_timestamp, timestamp__lt=impact_end).count()
        attendee_bonus = conversations.filter(speaker__role=Member.COMMUNITY, speaker__in=event.attendees, timestamp__gte=impact_end, timestamp__lt=bonus_end).count()
        trend_growth = previous_count / (baseline_count+1)
        predicted_count = previous_count * trend_growth
        if predicted_count == 0:
            raise RuntimeError("Predicted conversation count was zero")
        actual_growth = (new_count+attendee_bonus - predicted_count) / predicted_count
        event.impact = 100 * (actual_growth)
        if event.impact > 0 and event.impact < 1:
            event.impact = 1
        if event.impact < 0 and event.impact > -1:
            event.impact = -1
        if self.verbosity >= 2:
            print("--------------------------")
            print("event: %s %s" % (event.id, event.title))
            print("context: %s" % event_context)
            print("baseline: %s" % baseline_count)
            print("previous: %s" % previous_count)
            print("trend:    %s" % trend_growth)
            print("predicted:  %s" % predicted_count)
            print("current:  %s" % new_count)
            print("bonus:  %s" % attendee_bonus)
            print("growth:   %s" % actual_growth)
            print("impact:   %s" % event.impact)
        event.save()
        