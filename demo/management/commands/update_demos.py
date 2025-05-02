from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
import datetime
import re
import string
import names
import lorem
import math, random
from django.contrib.auth.models import User, Group
from django.db.models import Min
from django.conf import settings

from demo.models import Demonstration
from corm.models import *

class Command(BaseCommand):
    help = 'Update demo content'

    def handle(self, *args, **options):
        random.seed()
        for demo in Demonstration.objects.all():
            print("Updating %s" % demo.community)
            self.make_activity(demo.community)

            call_command('set_company_info', community=demo.community.id)
            call_command('level_check', community=demo.community.id)
            call_command('gift_impact', community=demo.community.id)
            call_command('make_connections', community=demo.community.id)
            call_command('make_suggestions', community=demo.community.id)

            if demo.status == demo.READY:
                demo.expires = datetime.datetime.utcnow() + datetime.timedelta(hours=settings.DEMO_DURATION_HOURS)
                demo.save()



    def make_activity(self, community):
        print("Making Conversations...")
        tags = [None]
        tag_weights = [70]
        members = community.member_set.all()
        member_count = members.count()
        for tag in Tag.objects.filter(community=community).order_by('last_changed'):
            tags.append(tag)
            tag_weights.append(tag_weights[-1]+5)
            if tag_weights[-1] >= 95:
                break
        members = members.annotate(activity_count=Count('speaker_in')).order_by('-activity_count')
        for from_member in random.sample(list(members[:int(member_count/2)]), int(member_count/200)):
            conversation_count = random.randint(1, 3)
            print("Adding %s conversations for %s" % (conversation_count, from_member))
            tag_counts = dict()
            for i in range(conversation_count):
                conversation_text = lorem.get_sentence(count=random.randint(1, 3), word_range=(8, 20))
                contact = random.choices(from_member.contact_set.all(), k=1)[0]
                channel = random.choices(contact.source.channel_set.all(), k=1)[0]
                conversation_date = datetime.datetime.utcnow() - datetime.timedelta(minutes=random.randrange(0, 60))

                conversation = Conversation.objects.create(community=community, source=channel.source, channel=channel, speaker=from_member, content=conversation_text, timestamp=conversation_date)
                if from_member.connections.count() > 1:
                    participant_count = random.randint(1, min(5, from_member.connections.count()))
                    participants = random.sample(list(from_member.connections.all()), participant_count)
                else:
                    participants = from_member.connections.all()
                for participant in participants:
                    Participant.objects.update_or_create(
                        community=community, 
                        conversation=conversation,
                        initiator=from_member,
                        member=participant,
                        timestamp=conversation_date
                    )
                Participant.objects.update_or_create(
                    community=community, 
                    conversation=conversation,
                    initiator=from_member,
                    member=from_member,
                    timestamp=conversation_date
                )

                convo_tag = random.choices(tags, cum_weights=tag_weights, k=1)[0]
                if convo_tag:
                    conversation.tags.add(convo_tag)
                    if convo_tag in tag_counts:
                        tag_counts[convo_tag] += 1
                    else:
                        tag_counts[convo_tag] = 1
                conversation.update_activity()

            for tag, count in tag_counts.items():
                if tag.name in ('greeting', 'thankful'):
                    continue
                if count > (conversation_count/2):
                    from_member.tags.add(tag)

        print("Making Contributions...")
        github = community.source_set.get(connector="corm.plugins.github")
        pr, created = ContributionType.objects.get_or_create(community=community, source=github, name="Pull Request")
        skip = random.randint(0, 20)
        if not skip:
            for contributor in random.sample(members, k=random.randint(0, int(member_count/100))):
                for i in range(random.choices([5, 4, 3, 2, 1], cum_weights=[5, 10, 20, 50, 90], k=1)[0]):
                    contribution_title = "PR: %s" % lorem.get_sentence(count=1, word_range=(5, 10))
                    contribution_date = datetime.datetime.utcnow() - datetime.timedelta(minutes=random.randrange(0, 60))
                    contribution_channel = random.choice(github.channel_set.all())
                    contribution = Contribution.objects.create(community=community, contribution_type=pr, title=contribution_title, source=github, channel=contribution_channel, author=contributor, timestamp=contribution_date)
                    feature_tag = random.choices(tags, cum_weights=tag_weights, k=1)[0]
                    if feature_tag:
                        contribution.tags.add(feature_tag)
                    contribution.update_activity()

        skip = random.randint(0, 10)
        if not skip:
            slack = community.source_set.get(connector="corm.plugins.slack")
            support, created = ContributionType.objects.get_or_create(community=community, source=slack, name="Support")
            for contributor in random.sample(members, k=random.randint(0, int(member_count/100))):
                contribution_count = 1
                from_conversations = contributor.speaker_in.filter(channel__source=slack, tags__name='thankful').all()
                for convo in random.choices(from_conversations, k=min(from_conversations.count(), contribution_count)):
                    contribution_date = datetime.datetime.utcnow() - datetime.timedelta(minutes=random.randrange(0, 60))
                    contribution_channel = random.choice(slack.channel_set.all())
                    contribution_title = "Helped in %s" % contribution_channel.name
                    contribution = Contribution.objects.create(community=community, contribution_type=support, title=contribution_title, source=slack, channel=contribution_channel, author=contributor, timestamp=convo.timestamp)
                    contribution.tags.set(convo.tags.all())
                    contribution.update_activity(convo.activity)

        for from_member in members:
            from_member.first_seen = from_member.activity.all().aggregate(first=Min('timestamp'))['first']
            if from_member.first_seen is not None:
                from_member.save()