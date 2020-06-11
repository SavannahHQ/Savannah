# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.db.models import Count
from django.shortcuts import reverse
from corm.models import Community, Member, Conversation, Tag, Contact, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag
from corm.models import pluralize
from notifications.signals import notify

class Command(BaseCommand):
    help = 'Create suggested maintenance actions'

    def handle(self, *args, **options):
        for community in Community.objects.all():
            self.make_merge_suggestions(community)

    def make_merge_suggestions(self, community):
        merge_count = 0
        # Check for duplicate usernames
        dups = Contact.objects.filter(member__community=community, email_address__isnull=False).values('email_address').annotate(dup_count=Count('member_id', distinct=True)).order_by('email_address').filter(dup_count__gt=1)
        print("Found %s duplicate email addresses" % len(dups))
        i = 0
        for dup in dups:
            if dup['dup_count'] > 1:
                print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, contact__email_address=dup['email_address']).order_by('id').distinct()
                destination_member = members[0]
                print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.update_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Matching contact emails: %s' % dup['email_address']})
                    if created:
                        merge_count += 1

        # Check for duplicate usernames
        dups = Contact.objects.filter(member__community=community).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by('detail').filter(dup_count__gt=1)
        print("Found %s duplicate usernames" % len(dups))
        i = 0
        for dup in dups:
            if dup['dup_count'] > 1:
                print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, contact__detail=dup['detail']).order_by('id').distinct()
                destination_member = members[0]
                print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.update_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Matching contact: %s' % dup['detail']})
                    if created:
                        merge_count += 1

        # Check for duplicate display names
        dups = Member.objects.filter(community=community).values('name').annotate(dup_count=Count('id', distinct=True)).order_by('name').filter(dup_count__gt=1)
        print("Found %s duplicate names" % len(dups))
        i = 0
        for dup in dups:
            if dup['dup_count'] > 1:
                print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, name=dup['name']).order_by('id').distinct()
                destination_member = members[0]
                print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.update_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Matching name: %s' % dup['name']})
                    if created:
                        merge_count += 1

        # Notify managers of new suggestions
        print("Suggested %s member merges" % merge_count)
        if merge_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                recipient=recipients, 
                verb="has %s new merge %s" % (merge_count, pluralize(merge_count, "suggestion")),
                level='info',
                icon_name="fas fa-people-arrows",
                link=reverse('member_merge_suggestions', kwargs={'community_id':community.id})
            )
