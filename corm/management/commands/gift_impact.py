# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.db.models import Count
from django.shortcuts import reverse
from corm.models import Community, Member, Conversation, Gift, GiftType
from corm.models import pluralize
from notifications.signals import notify

CONTEXT_TIMESPAN = datetime.timedelta(days=30)

class Command(BaseCommand):
    help = 'Calculate the impact of a gift on conversations'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)

    def handle(self, *args, **options):
        community_id = options.get('community_id')
        self.verbosity = options.get('verbosity')

        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            communities = [community]
        else:
            communities = Community.objects.all()

        for community in communities:
            self.calculate_gift_impact(community)

    def calculate_gift_impact(self, community):
        gifts = Gift.objects.filter(community=community)
        contributions = Conversation.objects.filter(speaker__community=community)

        gift_impacts = dict()
        for gift in gifts:
            sent = gift.sent_date
            if not sent:
                continue
            range_start = sent - CONTEXT_TIMESPAN
            range_end = sent + CONTEXT_TIMESPAN

            member_pre = contributions.filter(speaker=gift.member, timestamp__lt=sent, timestamp__gte=range_start).count()
            member_post = contributions.filter(speaker=gift.member, timestamp__gt=sent, timestamp__lte=range_end).count()
            if not member_pre:
                member_pre = 1
            member_rate = (member_post / member_pre) - 1
            if self.verbosity >= 2:
                print("Member rate for %s is %s" % (gift.member, member_rate))
            if self.verbosity >= 3:
                print("Member pre  %s - %s: %s\nMember post %s - %s: %s" % (range_start.date(), sent.date(), member_pre, sent.date(), range_end.date(), member_post))

            gift.impact = int(100 * member_rate)
            gift.save()

            if gift.gift_type not in gift_impacts:
                gift_impacts[gift.gift_type] = []
            gift_impacts[gift.gift_type].append(member_rate)

        if self.verbosity >= 2 and len(gift_impacts) > 0:
            print("-------------------------------------------")
        for gift_type, rates in gift_impacts.items():
            if len(rates) > 0:
                impact = int(100 * sum(rates) / len(rates))
                gift_type.impact = impact
                gift_type.save()
                if self.verbosity >= 2:
                    print("Impact score for %s is %s%%" % (gift_type, impact))