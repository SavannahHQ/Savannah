# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.shortcuts import reverse
from django.db.models import F, Q, Count, Max, Min

from corm.models import Community, Member, Conversation, Tag, Contact, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag
from corm.models import pluralize
from notifications.signals import notify

INACTIVITY_THRESHOLD_PREVIOUS_ACTIVITY = 50
INACTIVITY_THRESHOLD_PREVIOUS_DAYS = 90
INACTIVITY_THRESHOLD_DAYS = 30

RESUMING_THRESHOLD_PREVIOUS_ACTIVITY = 20
RESUMING_THRESHOLD_PREVIOUS_DAYS = 90
RESUMING_THRESHOLD_DAYS = 30

class Command(BaseCommand):
    help = 'Checks member activity and creates notifications for action'

    def handle(self, *args, **options):
        for community in Community.objects.all():
            self.check_for_inactivity(community)
            self.check_for_resuming_activity(community)
            self.check_for_first_contrib(community)

    def check_for_first_contrib(self, community):
        members = Member.objects.filter(community=community)
        members = members.annotate(first_contrib=Min('contribution__timestamp'))
        members = members.filter(first_contrib__gte=datetime.datetime.utcnow() - datetime.timedelta(days=1))
        for member in members:
            print("%s made their first contribution on %s" % (member.name, member.first_contrib))
            recipients = community.managers or community.owner
            notify.send(member, 
                recipient=recipients, 
                verb="made their first contribution to ",
                target=community,
                level='success',
                icon_name="fas fa-mail-bulk",
                link=reverse('member_profile', kwargs={'member_id':member.id})
            )

    def check_for_inactivity(self, community):
        members = Member.objects.filter(community=community, last_seen__lte=datetime.datetime.utcnow() - datetime.timedelta(days=INACTIVITY_THRESHOLD_DAYS), last_seen__gt=datetime.datetime.utcnow() - datetime.timedelta(days=INACTIVITY_THRESHOLD_DAYS+1))
        members = members.annotate(past_activity=Count('speaker_in', distinct=True, filter=Q(speaker_in__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=INACTIVITY_THRESHOLD_PREVIOUS_DAYS))))
        for member in members:
            if member.past_activity >= INACTIVITY_THRESHOLD_PREVIOUS_ACTIVITY:
                print("Member has stopped being active: %s (%s conversations in the last 90 days, not seen since %s)" % (member.name, member.past_activity, member.last_seen))
                recipients = community.managers or community.owner
                notify.send(member, 
                    recipient=recipients, 
                    verb="has been inactive since %s in " % member.last_seen.date(),
                    target=community,
                    level='warning',
                    icon_name="fas fa-user-clock",
                    link=reverse('member_profile', kwargs={'member_id':member.id})
                )

    def check_for_resuming_activity(self, community):
        members = Member.objects.filter(community=community, last_seen__gte=datetime.datetime.utcnow() - datetime.timedelta(days=1))
        members = members.annotate(last_activity=Max('speaker_in__timestamp', filter=Q(speaker_in__timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=1))))
        members = members.annotate(past_activity=Count('speaker_in', distint=True, filter=Q(speaker_in__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=RESUMING_THRESHOLD_PREVIOUS_DAYS))))
        for member in members:
            if member.past_activity >= RESUMING_THRESHOLD_PREVIOUS_ACTIVITY and member.last_activity is not None and member.last_activity < datetime.datetime.utcnow() - datetime.timedelta(days=RESUMING_THRESHOLD_DAYS):
                print("Member became active again: %s (previously seen %s)" % (member.name, member.last_activity))
                recipients = community.managers or community.owner
                notify.send(member, 
                    recipient=recipients, 
                    verb="has been active for the first time since %s in " % member.last_activity.date(),
                    target=community,
                    level='success',
                    icon_name="fas fa-user-check",
                    link=reverse('member_profile', kwargs={'member_id':member.id})
                )
