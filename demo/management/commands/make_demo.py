from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings
import datetime
import re
import string
import names
import lorem
import math, random
from django.contrib.auth.models import User, Group
from django.db.models import Min
from corm.models import *

# TODO:
# - Use sources:
#   - Github
#   - Slack
#   - Meetup
#   - RSS
#   - Twitter
# - Determine members shape
#   - Define 
#     - 2% core contributors 
#       - github, RSS
#       - 1 inactivity notification
#       - Add to feature project
#       - New core contributor insight
#     - 0.5% potential core 
#       - github, slack, RSS
#       - 1 level-up task suggestion
#       - Add to feature project
#       - New contributor insight
#     - 1% ambassadors 
#       - meetup, twitter, RSS
#       - 1 gift sent but not delivered
#       - Add to Ambassadors project
#     - 2 VIP 
#       - Twitter, Slack
#       - Member watch
#       - Member notes
#     - 2 problematic 
#       - slack
#       - Member watch
#       - Member notes
#       - 1 watch notification
#     - 1 hero 
#       - slack, twitter
#       - Lots of individual connections
#
#   - Use this when generating contributions, opportunities, tasks, suggestions, insights, etc
#   - Tag members according to this rather than randomly
#   - Set project levels based on this
# - Bulk-add conversations rather than one at a time
# - Generate events if an event-source is 
# - Generate notes on core, ambassador, problematic members
# - Generate insights
# - Generate suggestions
# - Update company names, domains and member emails


class Command(BaseCommand):
    help = 'Generate a Community with mock data'

    def add_arguments(self, parser):
        parser.add_argument('--community_id', type=int)
        parser.add_argument('--name', default="New", type=str)
        parser.add_argument('--owner_id', type=int)
        parser.add_argument('--size', default=200, type=int)
        parser.add_argument('--age', default=365, type=int)


    def handle(self, *args, **options):
        random.seed()
        self.community_id = options.get("community_id")
        self.community_name = options.get("name")
        try:
            if self.community_id:
                c = Community.objects.get(id=self.community_id)
            else:
                c = Community.objects.get(name=self.community_name+" Demo")
            community_id=c.id
            if c.managers is not None:
                c.managers.delete()
            c.delete()
        except Exception as e:
            print(e)
            #exit()
            community_id=None
        self.target_size = options.get('size')
        variance = int(self.target_size/10)
        self.member_count = int(random.randint(self.target_size - variance, self.target_size + variance))

        print("Creating new community \"%s\" with %s Members" % (self.community_name+" Demo", self.member_count))
        self.max_history_days = options.get('age')
        self.last_active_days = 7

        owner_id = options.get('owner_id')
        if owner_id:
            self.owner = User.objects.get(id=owner_id)
        else:
            self.owner = User.objects.get(username=settings.SYSTEM_USER)


        self.community = Community.objects.create(id=community_id, name=self.community_name+" Demo", owner=self.owner, status=Community.DEMO)
        self.community.bootstrap()

        self.tags, self.tag_weights = self.make_tags()
        self.sources = self.make_sources()
        self.companies, self.company_wieght = self.make_companies()
        self.make_projects()
        self.make_events()

        self.members = self.make_members()
        most_connected = Member.objects.filter(community=self.community).annotate(con_count=Count('connections')).order_by('-con_count')[0]
        self.manager_profile = ManagerProfile.objects.create(community=self.community, user=self.owner, member=most_connected)

        # self.make_notes()
        # self.make_notifications()
        self.make_connections()
        self.make_activity()
        self.make_watches()
        self.make_gifts()
        self.make_tasks()
        self.make_opportunities()

        call_command('set_company_info', community=self.community.id)
        call_command('level_check', community=self.community.id)
        call_command('gift_impact', community=self.community.id)
        call_command('event_impact', community=self.community.id)
        call_command('make_connections', community=self.community.id)
        call_command('make_suggestions', community=self.community.id)

        now = datetime.datetime.utcnow()
        year = now.year
        month = now.month
        for i in range(6):
            if month < 1:
                month = 12
                year -= 1
            call_command('make_reports', community=self.community.id, date="%04d-%02d" % (year, month))
            month -= 1


    def make_tags(self):
        print("Making Tags...")
        ambassador = Tag.objects.create(name="ambassador", community=self.community, color="ffaf9e")
        featurex = Tag.objects.create(name="feature-x", community=self.community, color="db85ff", keywords="feature x, x function")
        featurey = Tag.objects.create(name="feature-y", community=self.community, color="ffc61a", keywords="feature y, y function")
        thankful = self.community.tag_set.get(name="thankful")
        greeting = self.community.tag_set.get(name="greeting")
        feature_choices = [None, thankful, greeting, featurex, featurey]
        feature_weights = [70, 80, 85, 90, 95]
        return (feature_choices, feature_weights)

    def make_sources(self):
        print("Making Sources...")
        sources = list()

        ambassadors = Tag.objects.get(name="ambassador", community=self.community)
        slack = self.community.source_set.create(name="%s Chat"%self.community_name, connector="corm.plugins.slack", icon_name="fab fa-slack", enabled=True)
        slack.channel_set.create(name="general")
        slack.channel_set.create(name="random")
        slack.channel_set.create(name="community", tag=ambassadors)
        slack.channel_set.create(name="announcements")
        sources.append(slack)

        featurex = Tag.objects.get(name="feature-x", community=self.community)
        featurey = Tag.objects.get(name="feature-y", community=self.community)
        github = self.community.source_set.create(name="%s Org"%self.community_name, connector="corm.plugins.github", icon_name="fab fa-github", enabled=True)
        github.channel_set.create(name="Demo Src")
        github.channel_set.create(name="Demo Docs")
        github.channel_set.create(name="Feature X Src", tag=featurex)
        github.channel_set.create(name="Feature Y Src", tag=featurey)
        sources.append(github)

        discourse = self.community.source_set.create(name="%s Forum"%self.community_name, connector="corm.plugins.discourse", icon_name="fab fa-discourse", enabled=True)
        discourse.channel_set.create(name="General")
        discourse.channel_set.create(name="Features")
        discourse.channel_set.create(name="Help")
        sources.append(discourse)
        
        meetup = self.community.source_set.create(name="%s Meetups"%self.community_name, connector="corm.plugins.meetup", icon_name="fab fa-meetup", enabled=True)
        meetup.channel_set.create(name="San Francisco Meetup")
        meetup.channel_set.create(name="New York Meetup")
        meetup.channel_set.create(name="Atlanta Meetup")
        meetup.channel_set.create(name="London Meetup")
        meetup.channel_set.create(name="Paris Meetup")
        sources.append(meetup)
        
        random.shuffle(sources)
        return sources

    def make_companies(self):
        print("Making Companies...")
        customer = Tag.objects.create(name="customer", community=self.community, color="fbff32")
        staff_domain = self.community_name.replace(" ", "").lower() + ".com"
        staff_company = self.community.company_set.create(name=self.community_name, website="https://%s" % staff_domain, icon_url=settings.SITE_ROOT+'/static/img/company-default.png', is_staff=True)
        CompanyDomains.objects.create(company=staff_company, domain=staff_domain)

        large_co = self.community.company_set.create(name="Big Enterprise", website="https://enterprise.com", icon_url=settings.SITE_ROOT+'/static/img/company-default.png', is_staff=False, tag=customer)
        CompanyDomains.objects.create(company=large_co, domain="large.com")

        medium_co = self.community.company_set.create(name="Smart Stuff", website="https://smartstuff.com", icon_url=settings.SITE_ROOT+'/static/img/company-default.png', is_staff=False, tag=None)
        CompanyDomains.objects.create(company=medium_co, domain="smartstuff.com")

        prospect = Tag.objects.create(name="prospect", community=self.community, color="40f2dd")
        small_co = self.community.company_set.create(name="Indie Tech", website="https://indietech.com", icon_url=settings.SITE_ROOT+'/static/img/company-default.png', is_staff=False, tag=prospect)
        CompanyDomains.objects.create(company=small_co, domain="indietech.com")

        tiny_co = self.community.company_set.create(name="Startup Biz", website="https://startup.com", icon_url=settings.SITE_ROOT+'/static/img/company-default.png', is_staff=False, tag=None)
        CompanyDomains.objects.create(company=tiny_co, domain="startup.com")

        companies = [None, staff_company, large_co, medium_co, small_co, tiny_co]
        company_weights = [70, 89, 93, 96, 98, 99]
        return (companies, company_weights)

    def make_events(self):
        print("Making Events...")
        meetup = self.community.source_set.get(connector="corm.plugins.meetup")
        for channel in meetup.channel_set.all():
            #random.sample(self.members, k=random.randint(int(self.member_count/11), int(self.member_count/9))):
            event_count = random.randint(1, 10)
            for i in range(event_count):
                event_title = lorem.get_sentence(count=1, word_range=(5, 10))
                event_description = lorem.get_sentence(count=random.randint(1, 3), word_range=(8, 20))
                event_start = datetime.datetime.utcnow() + datetime.timedelta(days=30) - datetime.timedelta(days=random.randrange(1, self.max_history_days))
                event_end = event_start + datetime.timedelta(hours=random.randint(1,3))
                event_tag = random.choices(self.tags, cum_weights=[25, 25, 25, 50, 75], k=1)[0]
                event = Event.objects.create(
                    community=self.community,
                    source=meetup,
                    channel=channel,
                    title=event_title,
                    description = event_description,
                    start_timestamp=event_start,
                    end_timestamp=event_end,
                    tag=event_tag,
                )

    def make_opportunities(self):
        print("Making Opportunities...")
        slack = self.community.source_set.get(connector="corm.plugins.slack")
        discourse = self.community.source_set.get(connector="corm.plugins.discourse")
        meetup = self.community.source_set.get(connector="corm.plugins.meetup")
        github = self.community.source_set.get(connector="corm.plugins.github")
        support, created = ContributionType.objects.get_or_create(community=self.community, source=slack, name="Support")
        hosted, created = ContributionType.objects.get_or_create(community=self.community, source=meetup, name="Hosted")
        pr, created = ContributionType.objects.get_or_create(community=self.community, source=github, name="Pull Request")
        potential_supporters=self.community.member_set.filter(speaker_in__channel__source=slack)
        potential_hosts=self.community.member_set.filter(speaker_in__channel__source=meetup)
        potential_coders=self.community.member_set.filter(speaker_in__channel__source=github)
        # REJECTED = -2
        # DECLINED = -1
        # IDENTIFIED = 0
        # PROPOSED = 1
        # AGREED = 2
        # SUBMITTED = 3
        # COMPLETE = 4
        oppo_weights = [2, 5, 40, 60, 75, 80, 90]
        oppo_types = [
            (slack, potential_supporters, support, 'Provide support in %s'),
            (meetup, potential_hosts, hosted, 'Host an event at %s'),
            (github, potential_coders, pr, 'Submit patch to %s'),
        ]
        for source, members, contrib, title in oppo_types:
            # Opportunities
            for i in range(1, random.randint(3, 8)):
                member = random.choice(members)
                channel = random.choice(source.channel_set.all())
                status = random.choices(Opportunity.STATUS_CHOICES, cum_weights=oppo_weights, k=1)[0][0]
                if status in Opportunity.CLOSED_STATUSES:
                    closer = self.owner
                    closed_at = datetime.datetime.utcnow()
                else:
                    closer = None
                    closed_at = None
                Opportunity.objects.create(
                    created_by=self.owner,
                    community=self.community,
                    member=member,
                    source=channel.source,
                    contribution_type=contrib,
                    name=title % channel,
                    description=lorem.get_sentence(count=1, word_range=(8, 12)),
                    status=status,
                    closed_by=closer,
                    closed_at=closed_at,
                    deadline=datetime.datetime.utcnow() + datetime.timedelta(days=random.randint(-1, 30))
                )

    def make_projects(self):
        print("Making Projects...")
        default = self.community.default_project
        default.threshold_core=5
        default.save()

        ambassador_tag = self.community.tag_set.get(name="ambassador")
        ambassadors = self.community.project_set.create(name='Ambassadors Program', tag=ambassador_tag, threshold_core=3)
        ambassadors.channels.set(Channel.objects.filter(source__community=self.community, tag=ambassador_tag))

        feature_x_tag = self.community.tag_set.get(name="feature-x")
        project_x = self.community.project_set.create(name='Project X', tag=feature_x_tag, threshold_core=3)
        project_x.channels.set(Channel.objects.filter(source__community=self.community, tag=feature_x_tag))

        feature_y_tag = self.community.tag_set.get(name="feature-y")
        project_y = self.community.project_set.create(name='Project Y', tag=feature_y_tag, threshold_core=3)
        project_y.channels.set(Channel.objects.filter(source__community=self.community, tag=feature_y_tag))

    def make_gifts(self):
        print("Making Gifts...")
        thankyou = self.community.gifttype_set.create(name="Thank you pack", contents="Stickers and Socks")
        stickers = self.community.gifttype_set.create(name="Stickers", contents="Sheet of product stickers")
        tshirt = self.community.gifttype_set.create(name="T-shirt", contents="Branded T-Shirt")

        participants = Member.objects.filter(community=self.community)
        participants = participants.annotate(convo_count=Count('speaker_in'))
        participants = participants.filter(convo_count__gt=1)

        gifts = [None, stickers, thankyou, tshirt]
        gift_weights = [70, 80, 90, 95]
        sent = list()
        for member in participants:
            gift = random.choices(gifts, cum_weights=gift_weights, k=1)[0]
            if gift is not None:
                gift_date = member.first_seen + datetime.timedelta(days=int((member.last_seen - member.first_seen).days / 2) - 7)
                sent.append(Gift.objects.create(community=self.community, member=member, gift_type=gift, sent_date=gift_date, received_date=gift_date+datetime.timedelta(days=7), reason="For Demo purposes"))
        # Pick 5 randomly for followup
        for gift in random.choices(sent, k=5):
            gift.received_date = None
            gift.save()

    def make_tasks(self):
        print("Making Tasks...")
        # Upcoming Followups
        for member in random.choices(self.members, k=2):
            task_name = "Follow up with %s" % member.name
            due_date = datetime.datetime.utcnow() + datetime.timedelta(days=random.randrange(3, 15))
            task = Task.objects.create(community=self.community, name=task_name, detail="", owner=self.owner, project=self.community.default_project, due=due_date)
            task.stakeholders.add(member)
        # Past due Followups
        for member in random.choices(self.members, k=1):
            task_name = "Follow up with %s" % member.name
            due_date = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, 4))
            task = Task.objects.create(community=self.community, name=task_name, detail="", owner=self.owner, project=self.community.default_project, due=due_date)
            task.stakeholders.add(member)

        # Feature contributor
        feature_project = Project.objects.get(community=self.community, name="Project X")
        contributors = Member.objects.filter(community=self.community)
        contributors = contributors.annotate(contrib_count=Count('contribution', filter=Q(contribution__channel__in=feature_project.channels.all())))
        contributors = contributors.filter(contrib_count__gt=0)
        if contributors.count() > 0:
            recipient = contributors.order_by('-contrib_count')[0]
            due_date = datetime.datetime.utcnow() + datetime.timedelta(days=3)
            gift = Task.objects.create(community=self.community, name="Send t-shirt", detail="They've made contributions to Project X", owner=self.owner, project=feature_project, due=due_date)
            gift.stakeholders.add(recipient)

        # Ambassador invite
        ambassador_project = Project.objects.get(community=self.community, name="Ambassadors Program")
        candidates = Member.objects.filter(community=self.community).exclude(tags=ambassador_project.tag)
        candidates = candidates.annotate(connection_count=Count('connections'))
        candidates = candidates.filter(connection_count__gt=0)
        if candidates.count() > 0:
            candidate = candidates.order_by('-connection_count')[0]
            due_date = datetime.datetime.utcnow() + datetime.timedelta(days=7)
            invite = Task.objects.create(community=self.community, name="Invite to join Ambassadors", detail="They are highly connected with other community members", owner=self.owner, project=ambassador_project, due=due_date)
            invite.stakeholders.add(candidate)

    def make_members(self):
        members = list()
        print("Making Members...")
        for i in range(self.member_count):
            member_name = names.get_full_name()
            first_seen = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, self.max_history_days))
            last_seen = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, self.last_active_days))
            if first_seen > last_seen:
                tmp = first_seen
                first_seen = last_seen
                last_seen = tmp
            role_chance = random.randint(0, 1000)
            if role_chance < 10:
                role = Member.BOT
                member_name = member_name.split(" ")[0] + " Bot"
            else:
                role = Member.COMMUNITY
            member_email = None
            company = random.choices(self.companies, cum_weights=self.company_wieght, k=1)[0]
            if company is not None:
                company_domain = CompanyDomains.objects.filter(company=company)[0]
                member_email = member_name.split(" ")[0].lower() + "@" + company_domain.domain
            new_member = self.community.member_set.create(name=member_name, email_address=member_email, role=role, first_seen=first_seen, last_seen=last_seen)
            members.append(new_member)

            username = new_member.name.lower().replace(" ", "_")
            contact_counts = [1, 2, 3]
            contact_weights = [50, 80, 90]
            contact_count = random.choices(contact_counts, cum_weights=contact_weights, k=1)[0]
            source_weights = [10, 30, 70, 95]
            for source in random.choices(self.sources, cum_weights=source_weights, k=contact_count):
                Contact.objects.get_or_create(member=new_member, source=source, detail=username, origin_id='demo-%s'%new_member.id)
        return members

    def make_watches(self):
        print("Making Member Watches...")
        for member in random.choices(self.members, k=5):
            last_convo = Conversation.objects.filter(speaker=member).order_by('-timestamp')[0]
            MemberWatch.objects.create(manager=self.owner, member=member, last_seen=last_convo.timestamp, last_channel=last_convo.channel)

    def make_connections(self):
        print("Making Connections...")
        max_con = int(self.member_count / 5)
        convar = int(max_con/10)
        hero_count = max(2, int(math.log10(self.member_count)))
        connect = dict()
        print("Making %s heros with %s connections..." % (hero_count, max_con))
        for hero in random.sample(self.members, k=hero_count):
            if hero not in connect:
                connect[hero] = random.randint(max_con-convar, max_con+convar)

        core_con = int(max_con / 10)+1
        print("Making %s core with %s connections..." % (hero_count*5, core_con))
        for core in random.sample(self.members, k=hero_count*5):
            if core not in connect:
                connect[core] = random.randint(core_con-convar, core_con+convar)

        par_con = int(max_con / 40)+1
        print("Making %s participants with %s connections..." % (hero_count*10, par_con))
        for participant in random.sample(self.members, k=hero_count*10):
            if participant not in connect:
                connect[participant] = random.randint(par_con-convar, par_con+convar)

        vis_con = int(max_con / 60)+1
        print("Making %s visitors with %s connections..." % (hero_count*20, vis_con))
        for visitor in random.sample(self.members, k=hero_count*30):
            if visitor not in connect:
                connect[visitor] = random.randint(vis_con-convar, vis_con+convar)

        ambassador_tag = self.community.tag_set.get(name="ambassador", community=self.community)
        for from_member, connection_count in connect.items():
            if connection_count < 1:
                connection_count = 1
            if connection_count > self.member_count:
                connection_count = self.member_count
            to_members = random.sample(self.members, k=connection_count)
            for to_member in to_members:
                if to_member in connect:
                    continue
                if from_member.id != to_member.id:
                    possible_start = max(from_member.first_seen, to_member.first_seen)
                    possible_end = min(from_member.last_seen, to_member.last_seen)
                    possible_days = (possible_end-possible_start).days
                    if possible_days > hero_count:# Hack to scale up the required overlap based on membership size
                        connected_date = possible_start +  datetime.timedelta(days=random.randrange(0, possible_days))
                        from_member.add_connection(to_member, timestamp=connected_date)
            if connection_count > 8 and random.randint(1, 3) > 2:
                from_member.tags.add(ambassador_tag)
        return

    def make_activity(self):
        print("Making Conversations...")
        for from_member in self.members:
            conversation_count = random.randint(1, 10)
            tag_counts = dict()
            convo_range = (from_member.last_seen-from_member.first_seen).days+1
            for i in range(conversation_count):
                conversation_text = lorem.get_sentence(count=random.randint(1, 3), word_range=(8, 20))
                contact = random.choices(from_member.contact_set.all(), k=1)[0]
                channel = random.choices(contact.source.channel_set.all(), k=1)[0]
                conversation_date = from_member.last_seen - datetime.timedelta(days=random.randrange(0, convo_range))

                conversation = Conversation.objects.create(community=self.community, source=channel.source, channel=channel, speaker=from_member, content=conversation_text, timestamp=conversation_date)

                if from_member.connections.count() > 1:
                    participant_count = random.randint(1, min(5, from_member.connections.count()))
                    participants = random.sample(list(from_member.connections.all()), participant_count)
                else:
                    participants = from_member.connections.all()
                for participant in participants:
                    Participant.objects.update_or_create(
                        community=self.community, 
                        conversation=conversation,
                        initiator=from_member,
                        member=participant,
                        timestamp=conversation_date
                    )

                Participant.objects.update_or_create(
                    community=self.community, 
                    conversation=conversation,
                    initiator=from_member,
                    member=from_member,
                    timestamp=conversation_date
                )

                convo_tag = random.choices(self.tags, cum_weights=self.tag_weights, k=1)[0]
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


        print("Making Pull Requests...")
        github = self.community.source_set.get(connector="corm.plugins.github")
        pr, created = ContributionType.objects.get_or_create(community=self.community, source=github, name="Pull Request")
        for contributor in random.sample(self.members, k=random.randint(int(self.member_count/11), int(self.member_count/9))):
            for i in range(random.choices([5, 4, 3, 2, 1], cum_weights=[5, 10, 20, 50, 90], k=1)[0]):
                contribution_title = "PR: %s" % lorem.get_sentence(count=1, word_range=(5, 10))
                contribution_date = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, self.max_history_days))
                contribution_channel = random.choice(github.channel_set.all())
                contribution = Contribution.objects.create(community=self.community, contribution_type=pr, title=contribution_title, source=github, channel=contribution_channel, author=contributor, timestamp=contribution_date)
                if contribution_channel.tag:
                    contribution.tags.add(contribution_channel.tag)
                contribution.update_activity()

        print("Making Support...")
        slack = self.community.source_set.get(connector="corm.plugins.slack")
        support, created = ContributionType.objects.get_or_create(community=self.community, source=slack, name="Support")
        thankfuls = Conversation.objects.filter(channel__source=slack, tags__name='thankful')
        thankful_count = thankfuls.count()
        for convo in random.sample(list(thankfuls), k=random.randint(int(thankful_count/5), int(thankful_count/2))):
            contribution_date = convo.timestamp
            contribution_channel = convo.channel
            contribution_title = "Helped in %s" % contribution_channel.name
            contribution = Contribution.objects.create(community=self.community, contribution_type=support, title=contribution_title, source=slack, channel=contribution_channel, author=contributor, timestamp=convo.timestamp)
            contribution.tags.set(convo.tags.exclude(name='thankful'))
            contribution.update_activity(convo.activity)

        print("Making Attendees...")
        meetup = self.community.source_set.get(connector="corm.plugins.meetup")
        for attending_member in random.sample(self.members, k=random.randint(int(self.member_count/11), int(self.member_count/9))):
            event_count = random.randint(1, 5)
            tag_counts = dict()
            convo_range = (from_member.last_seen-from_member.first_seen).days+1
            channel = random.choices(meetup.channel_set.all(), k=1)[0]
            for i in range(event_count):
                event = random.choices(self.community.event_set.filter(source=meetup, channel=channel), k=1)[0]
                attendee = EventAttendee.objects.create(community=self.community, event=event, member=attending_member, timestamp=event.start_timestamp)
                attendee.update_activity()

        print("Making Hosts...")
        hosted, created = ContributionType.objects.get_or_create(community=self.community, source=meetup, name="Hosted")
        for event in self.community.event_set.all():
            if event.rsvp.all().count() > 0:
                attendee = random.choices(event.rsvp.all(), k=1)[0]
                contribution_title = "Hosted %s" % lorem.get_sentence(count=1, word_range=(3, 6))
                contribution_date = datetime.datetime.utcnow() - datetime.timedelta(days=random.randrange(1, self.max_history_days))
                contribution_channel = attendee.event.channel
                contribution = Contribution.objects.create(community=self.community, contribution_type=hosted, title=contribution_title, source=meetup, channel=contribution_channel, author=attendee.member, timestamp=contribution_date)
                contribution.update_activity()
                attendee.role = EventAttendee.HOST
                attendee.save()

        for from_member in self.members:
            from_member.first_seen = from_member.activity.all().aggregate(first=Min('timestamp'))['first']
            if from_member.first_seen:
                from_member.save()