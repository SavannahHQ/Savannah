from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
import names
import lorem
import math, random
from django.contrib.auth.models import User, Group
from corm.models import *

class Command(BaseCommand):
    help = 'Generate a Community with mock data'

    def add_arguments(self, parser):
        parser.add_argument('--name', default="Demo", type=str)
        parser.add_argument('--owner_id', type=int)
        parser.add_argument('--size', default=200, type=int)


    def handle(self, *args, **options):
        random.seed()
        community_name = options.get("name")
        try:
            c = Community.objects.get(name=community_name)
            community_id=c.id
            c.delete()
        except:
            community_id=None
        print("Creating new community: %s" % community_name)
        target_size = options.get('size')

        owner_id = options.get('owner_id')
        if owner_id:
            owner = User.objects.get(id=owner_id)
        else:
            owner = User.objects.filter(is_staff=True).order_by('id')[0]

        community = Community.objects.create(id=community_id, name=community_name, owner=owner, icon_path='/static/savannah/Savannah32.png')

        thankful = Tag.objects.create(name="thankful", community=community, color="aff5ab", keywords="thanks, thank you, thx, thank yo")
        greeting = Tag.objects.create(name="greeting", community=community, color="abdef5", keywords="welcome, hi, hello")
        ambassador = Tag.objects.create(name="ambassador", community=community, color="ffaf9e")
        featurex = Tag.objects.create(name="feature-x", community=community, color="d0c6fb")
        featurey = Tag.objects.create(name="feature-y", community=community, color="fcebb8")
        feature_choices = [None, featurex, featurey]
        feature_weights = [70, 90, 95]

        sources = list()
        slack = community.source_set.create(name="Demo Chat", connector="corm.plugins.slack", icon_name="fab fa-slack")
        slack.channel_set.create(name="general")
        slack.channel_set.create(name="random")
        slack.channel_set.create(name="community")
        slack.channel_set.create(name="announcements")
        sources.append(slack)

        github = community.source_set.create(name="Demo Org", connector="corm.plugins.github", icon_name="fab fa-github")
        github.channel_set.create(name="Demo Src")
        github.channel_set.create(name="Demo Docs")
        sources.append(github)

        discourse = community.source_set.create(name="Demo Forum", connector="corm.plugins.discourse", icon_name="fab fa-discourse")
        discourse.channel_set.create(name="General")
        discourse.channel_set.create(name="Features")
        discourse.channel_set.create(name="Help")
        sources.append(discourse)
        
        random.shuffle(sources)

        members = list()
        member_count = int((target_size/2) + random.randint(0, target_size))
        print("Generating %s Members..." % member_count)
        for i in range(member_count):
            member_name = names.get_full_name()
            first_seen = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, 180))
            last_seen = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, 60))
            if first_seen > last_seen:
                tmp = first_seen
                first_seen = last_seen
                last_seen = tmp
            role_chance = random.randint(0, 1000)
            if role_chance < 10:
                role = Member.BOT
                member_name = member_name.split(" ")[0] + " Bot"
                member_email = None
            elif role_chance < 100:
                role = Member.STAFF
                member_email = member_name.split(" ")[0].lower() + "@democorp.com"
            else:
                role = Member.COMMUNITY
                member_email = member_name.split(" ")[0].lower() + "@community.org"
            new_member = community.member_set.create(name=member_name, email_address=member_email, role=role, first_seen=first_seen, last_seen=last_seen)
            members.append(new_member)

            username = new_member.name.lower().replace(" ", "_")
            contact_counts = [1, 2, 3]
            contact_weights = [50, 80, 90]
            contact_count = random.choices(contact_counts, cum_weights=contact_weights, k=1)[0]
            source_weights = [10, 30, 70]
            for source in random.choices(sources, cum_weights=source_weights, k=contact_count):
                Contact.objects.get_or_create(member=new_member, source=source, detail=username)

        print("Generating Conversations...")
        connection_counts = [1, 1, 2, 4, 8, 16, 32, 64, 128]
        connection_weights = [75, 80, 85, 90, 93, 95, 97, 98, 99]
        for from_member in members:
            connection_count = member_count+1
            while connection_count >= member_count:
                connection_count = random.choices(connection_counts, cum_weights=connection_weights, k=1)[0]
            to_members = random.sample(members, k=connection_count)
            for to_member in to_members:
                if from_member.id != to_member.id:
                    connected_date = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, 180))
                    from_member.add_connection(to_member, source=random.sample(sources, k=1)[0], timestamp=connected_date)
            if connection_count > 8 and random.randint(1, 3) > 2:
                from_member.tags.add(ambassador)

            conversation_count = random.randint(1, 10)
            tag_counts = dict()
            for i in range(conversation_count):
                conversation_text = lorem.get_sentence(count=random.randint(1, 3), word_range=(8, 20))
                contact = random.choices(from_member.contact_set.all(), k=1)[0]
                channel = random.choices(contact.source.channel_set.all(), k=1)[0]
                conversation_date = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, 180))

                conversation = Conversation.objects.create(channel=channel, speaker=from_member, content=conversation_text, timestamp=conversation_date)
                if from_member.connections.count() > 1:
                    participant_count = random.randint(1, min(5, from_member.connections.count()))
                    participants = random.sample(list(from_member.connections.all()), participant_count)
                else:
                    participants = from_member.connections.all()
                conversation.participants.set(participants)
                conversation.participants.add(from_member)

                feature_tag = random.choices(feature_choices, cum_weights=feature_weights, k=1)[0]
                if feature_tag:
                    conversation.tags.add(feature_tag)
                    if feature_tag in tag_counts:
                        tag_counts[feature_tag] += 1
                    else:
                        tag_counts[feature_tag] = 1
            for tag, count in tag_counts.items():
                if count > (conversation_count/2):
                    from_member.tags.add(tag)

        print("Generating Contributions...")
        pr, created = ContributionType.objects.get_or_create(community=community, source=github, name="Pull Request")
        for contributor in random.sample(members, k=random.randint(int(member_count/11), int(member_count/9))):
            for i in range(random.choices([5, 4, 3, 2, 1], cum_weights=[5, 10, 20, 50, 90], k=1)[0]):
                contribution_title = lorem.get_sentence(count=1, word_range=(5, 20))
                contribution_date = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, 120))
                contribution_channel = random.choice(github.channel_set.all())
                contribution = Contribution.objects.create(community=community, contribution_type=pr, title=contribution_title, channel=contribution_channel, author=contributor, timestamp=contribution_date)

                feature_tag = random.choices(feature_choices, cum_weights=feature_weights, k=1)[0]
                if feature_tag:
                    contribution.tags.add(feature_tag)

