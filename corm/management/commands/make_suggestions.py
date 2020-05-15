# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.db.models import Count
from corm.models import Community, Member, Conversation, Tag, Contact, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag
from notifications.signals import notify

class Command(BaseCommand):
    help = 'Create suggested maintenance actions'

    def handle(self, *args, **options):
        for community in Community.objects.all():
            self.make_merge_suggestions(community)

    def make_merge_suggestions(self, community):
        dups = Contact.objects.filter(member__community=community).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by('detail').filter(dup_count__gt=1)
        print("Found %s duplicates" % len(dups))
        i = 0
        merge_count = 0
        for dup in dups:
            if dup['dup_count'] > 1:
                print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(contact__detail=dup['detail']).order_by('id').distinct()
                destination_member = members[0]
                print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.update_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Matching contact: %s' % dup['detail']})
                    if created:
                        merge_count += 1
        print("Suggested %s member merges" % merge_count)
        if merge_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                target=community, 
                recipient=recipients, 
                verb="%s new merge suggestions" % merge_count,
                level='info',
                icon_name="fas fa-person-arrows",
                link='/suggestions/%s/' % community.id)
