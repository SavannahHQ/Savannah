# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.shortcuts import reverse
from django.db.models import F, Q, Count, Max

from corm.models import Community, Member, Conversation, Tag, Contact, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag
from corm.models import pluralize
from notifications.signals import notify

class Command(BaseCommand):
    help = 'Checks member activity and creates notifications for action'

    def handle(self, *args, **options):
        for community in Community.objects.all():
            #self.check_for_inactivity(community)
            self.check_for_resuming_activity(community)

    def check_for_inactivity(self, community):
        members = Member.objects.filter(community=community, last_seen__lte=datetime.datetime.utcnow() - datetime.timedelta(days=14), last_seen__gt=datetime.datetime.utcnow() - datetime.timedelta(days=15)).annotate(past_activity=Count('conversation', distint=True, filter=Q(conversation__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=90))))
        for member in members:
            if member.past_activity >= 50:
                print("Member has stopped being active: %s (%s conversations in the last 90 days, not seen since %s)" % (member.name, member.past_activity, member.last_seen))
                recipients = community.managers or community.owner
                notify.send(member, 
                    recipient=recipients, 
                    verb="has been inactive since %s" % member.last_seen.date(),
                    level='warning',
                    icon_name="fas fa-user",
                    link=reverse('member_profile', kwargs={'member_id':member.id})
                )

    def check_for_resuming_activity(self, community):
        members = Member.objects.filter(community=community, last_seen__gte=datetime.datetime.utcnow() - datetime.timedelta(days=1)).annotate(last_activity=Max('conversation__timestamp', filter=Q(conversation__timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=1))))
        for member in members:
            if member.last_activity is not None and member.last_activity < datetime.datetime.utcnow() - datetime.timedelta(days=7):
                print("Member became active again: %s (previously seen %s)" % (member.name, member.last_activity))
                recipients = community.managers or community.owner
                notify.send(member, 
                    recipient=recipients, 
                    verb="has been active for the first time since %s" % member.last_activity.date(),
                    level='success',
                    icon_name="fas fa-user",
                    link=reverse('member_profile', kwargs={'member_id':member.id})
                )
