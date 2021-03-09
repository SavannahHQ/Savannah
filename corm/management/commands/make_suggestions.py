# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.db.models import Count
from django.shortcuts import reverse
from corm.models import Community, Member, Conversation, Tag, Contact, Source, ContributionType, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag, SuggestConversationAsContribution
from corm.models import pluralize
from notifications.signals import notify

class Command(BaseCommand):
    help = 'Create suggested maintenance actions'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)

    def handle(self, *args, **options):
        community_id = options.get('community_id')

        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            communities = [community]
        else:
            communities = Community.objects.all()

        for community in communities:
            self.make_merge_suggestions(community)
            self.make_conversation_helped_suggestions(community)

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
                    suggestion, created = SuggestMemberMerge.objects.get_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Email match: %s' % dup['email_address']})
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
                    suggestion, created = SuggestMemberMerge.objects.get_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Username match: %s' % dup['detail']})
                    if created:
                        merge_count += 1

        # Check for duplicate display names
        dups = Member.objects.filter(community=community).values('name').annotate(dup_count=Count('id', distinct=True)).order_by('name').filter(dup_count__gt=1)
        print("Found %s duplicate names" % len(dups))
        i = 0
        for dup in dups:
            names = dup['name'].split(' ')
            if dup['dup_count'] > 1 and len(names) > 1:
                print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, name=dup['name']).order_by('id').distinct()
                destination_member = members[0]
                print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.get_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Full name match: %s' % dup['name']})
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

    def make_conversation_helped_suggestions(self, community):
        suggestion_count = 0
        try:
            thankful = Tag.objects.get(community=community, name="thankful")
        except:
            print("%s has no #thankful tag" % community)
            return

        # Only look at thankful converstions
        convos = Conversation.objects.filter(speaker__community=community, tags=thankful, contribution=None, contribution_suggestions=None)

        # Exclude greetings as they are usually the start of a conversation
        try:
            greeting = Tag.objects.get(community=community, name="greeting")
            convos = convos.exclude(tags=greeting)
        except:
            print("%s has no #greeting tag" % community)

        # From Chat-style sources
        chat_sources = Source.objects.filter(community=community, connector__in=('corm.plugins.slack', 'corm.plugins.discord', 'corm.plugins.reddit'))
        convos = convos.filter(channel__source__in=chat_sources)

        # Involving only the speaker and one other participant
        convos = convos.annotate(participant_count=Count('participants')).filter(participant_count=2)
        convos = convos.select_related('channel').order_by('channel', '-timestamp')

        print("%s potential support contributions in %s" % (convos.count(), community))
        positive_words = ('!', ':)', 'smile', 'smiling', 'fixed', 'solved', 'helped', 'worked', 'wasn\'t working', 'answer')
        negative_words = ('?', ':(', 'sad', 'frown', 'broken', 'fail', 'help me', 'helpful', 'error', 'not working', 'isn\t working', 'question', 'please', 'welcome', 'but')
        last_helped = None
        last_channel = None
        for convo in convos:
            if convo.content is None:
                continue
            if last_channel != convo.channel:
                last_helped = None
            last_channel = convo.channel

            # Attempt to see if this was for something helpful
            content = convo.content.lower()
            content_words = content.split(" ")
            score = 0
            if len(content_words) < 20:
                score += 1
            if len(content_words) > 50:
                score -= 1
            for word in positive_words:
                if word in content:
                    score += 1
            for word in negative_words:
                if word in content:
                    score -= 1

            # Support is more likely to be given to community than to staff or bots
            if score >= 1 and convo.speaker.role != Member.COMMUNITY:
                score -= 1

            # Only suggest for high positive scores
            if score < 2:
                continue

            # Exclude conversations that are part of another contribution's thread
            if convo.thread_start:
                if convo.thread_start.contribution:
                    continue

            # Don't count multiple instances in a row helping the same person
            if last_helped == convo.speaker:
                continue
            last_helped = convo.speaker

            helped, created = ContributionType.objects.get_or_create(
                community=community,
                source_id=convo.channel.source_id,
                name="Support",
            )
            supporter = convo.participants.exclude(id=convo.speaker.id)[0]
            suggestion, created = SuggestConversationAsContribution.objects.get_or_create(
                community=community,
                reason="%s gave support to %s" % (supporter, convo.speaker),
                conversation=convo,
                contribution_type=helped,
                source_id=convo.channel.source_id,
                score=score,
                title="Helped %s in %s" % (convo.speaker, convo.channel),
            )
            if created:
                suggestion_count += 1

        print("Suggested %s contributions" % suggestion_count)
        if suggestion_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                recipient=recipients, 
                verb="has %s new contribution %s" % (suggestion_count, pluralize(suggestion_count, "suggestion")),
                level='info',
                icon_name="fas fa-mail-bulk",
                link=reverse('conversation_as_contribution_suggestions', kwargs={'community_id':community.id})
            )