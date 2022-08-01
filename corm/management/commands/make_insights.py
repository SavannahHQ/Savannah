# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import os
import sys
import datetime
import operator
from functools import reduce

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.feature_extraction import text 

from django.db.models import Count, Q, Min, Max, QuerySet, F
from django.db.models.functions import Lower
from django.shortcuts import reverse
from django.contrib.auth.models import Group
from corm.models import Activity, Community, Member, Conversation, Tag, Contact, Source, Channel, ContributionType, Project, MemberLevel
from corm.models import Insight
from corm.models import pluralize

SUGGESTION_SEARCH_SPAN = 90


class Command(BaseCommand):
    help = 'Create suggested maintenance actions'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--timespan', dest='timespan', type=int)

    def handle(self, *args, **options):
        community_id = options.get('community_id')
        self.timespan = options.get('timespan')
        self.verbosity = options.get('verbosity')

        if not self.timespan:
            self.timespan = SUGGESTION_SEARCH_SPAN
        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            communities = [community]
        else:
            communities = Community.objects.filter(status=Community.ACTIVE)

        for community in communities:
            self.make_source_insights(community)
            self.make_level_insights(community)
            self.make_tag_insights(community)
            self.make_new_member_insights(community)
            self.make_first_contrib(community)

    def make_new_member_insights(self, community):
        offset_days = 7
        trend_days = 60

        trend_start = datetime.datetime.utcnow() - datetime.timedelta(days=(offset_days*2)+trend_days)
        trend_end = baseline_start = datetime.datetime.utcnow() - datetime.timedelta(days=offset_days*2)
        baseline_end = insight_start = datetime.datetime.utcnow() - datetime.timedelta(days=offset_days)
        insight_end = datetime.datetime.utcnow()
        sources = Source.objects.filter(community=community)
        sources = sources.annotate(trend_count=Count('contact__member', distinct=True, filter=Q(contact__member__first_seen__gt=trend_start, contact__member__last_seen__lte=trend_end, contact__member__last_seen__isnull=False)))
        sources = sources.annotate(baseline_count=Count('contact__member', distinct=True, filter=Q(contact__member__first_seen__gt=baseline_start, contact__member__first_seen__lte=baseline_end, contact__member__last_seen__isnull=False)))
        sources = sources.annotate(insight_count=Count('contact__member', distinct=True, filter=Q(contact__member__first_seen__gt=insight_start, contact__member__first_seen__lte=insight_end, contact__member__last_seen__isnull=False)))
        sources = sources.filter(baseline_count__gt=0, insight_count__gt=0, trend_count__gt=0)

        for source in sources:
            baseline_diff = 100 * (source.insight_count - source.baseline_count)/source.baseline_count
            trend = (source.trend_count / trend_days) * offset_days
            trend_diff = 100 * (source.insight_count - trend)/trend
            if self.verbosity >= 2:
                print("%s [baseline]: %s -> %s (%s%%)" % (source.name, source.baseline_count, source.insight_count, baseline_diff))
                print("%s [trend]: %s -> %s (%s%%)" % (source.name, trend, source.insight_count, trend_diff))
            if source.insight_count > 5 and baseline_diff >= 25 and trend_diff >= 50:
                uid = 'new-members:%s' % source.id
                try:
                    last_insight = Insight.objects.filter(community=community, uid=uid).order_by('-timestamp')[0]
                    days_since_last_insight = (datetime.datetime.utcnow() - last_insight.timestamp).days
                    if days_since_last_insight < offset_days:
                        return
                except:
                    pass
                insight_title = 'New users coming in from <b>%s</b>' % source.connector_name
                if source.name == source.connector_name:
                    insight_text = '<p>Your community has added %s new members over the last %s days from <b>%s</b></p>' % (source.insight_count, offset_days, source.name, )
                else:
                    insight_text = '<p>Your community has added %s new members over the last %s days from <b>%s</b> on <b>%s</b>.</p>' % (source.insight_count, offset_days, source.name, source.connector_name)
                insight_text += '<p>This is a %0.2f%% increase over previous %s days, and a %0.2f%% increase over the %s days prior to that.<p>' % (baseline_diff, offset_days, trend_diff, trend_days)

                tags = Tag.objects.filter(community=community)
                tags = tags.annotate(convo_count=Count('conversation', filter=Q(conversation__channel__source=source, conversation__speaker__first_seen__gte=insight_start)))
                tags = tags.filter(convo_count__gte=5)
                if tags.count() > 0:
                    insight_text += "<p>Their primary topics were:<ul>"
                    for tag in tags.order_by('-convo_count')[:10]:
                        insight_text += '<li><span class="tag-pill text-nowrap" style="background-color: #%s; "><span class="tag-text" style="color: #%saa;">%s</span></span> (%s comments)</li>' % (tag.color, tag.color, tag.name, tag.convo_count)
                    insight_text += "</ul></p>"
                Insight.create(
                    community=community, 
                    recipient=community.managers or community.owner,
                    uid=uid,
                    level=Insight.InsightLevel.SUCCESS,
                    title=insight_title,
                    text=insight_text,
                    cta="View Members",
                    link=reverse('all_members', kwargs={'community_id':community.id})+"?clear=all&timespan=%s&sort=-first_seen&source=%s" % (offset_days, source.id)
                )

    def make_tag_insights(self, community):
        offset_days = 7
        trend_days = 60

        trend_start = datetime.datetime.utcnow() - datetime.timedelta(days=(offset_days*2)+trend_days)
        trend_end = baseline_start = datetime.datetime.utcnow() - datetime.timedelta(days=offset_days*2)
        baseline_end = insight_start = datetime.datetime.utcnow() - datetime.timedelta(days=offset_days)
        insight_end = datetime.datetime.utcnow()
        tags = Tag.objects.filter(community=community)
        tags = tags.annotate(trend_count=Count('conversation', filter=Q(conversation__timestamp__gt=trend_start, conversation__timestamp__lte=trend_end)))
        tags = tags.annotate(baseline_count=Count('conversation', filter=Q(conversation__timestamp__gt=baseline_start, conversation__timestamp__lte=baseline_end)))
        tags = tags.annotate(insight_count=Count('conversation', filter=Q(conversation__timestamp__gt=insight_start, conversation__timestamp__lte=insight_end)))
        tags = tags.filter(baseline_count__gt=0, insight_count__gt=0, trend_count__gt=0)

        for tag in tags:
            baseline_diff = 100 * (tag.insight_count - tag.baseline_count)/tag.baseline_count
            trend = (tag.trend_count / trend_days) * offset_days
            trend_diff = 100 * (tag.insight_count - trend)/trend
            if tag.insight_count > 5 and baseline_diff > 10 and trend_diff > 50 and trend_diff > baseline_diff:
                if self.verbosity >= 2:
                    print("%s [baseline]: %s -> %s (%s%%)" % (tag.name, tag.baseline_count, tag.insight_count, baseline_diff))
                    print("%s [trend]: %s -> %s (%s%%)" % (tag.name, trend, tag.insight_count, trend_diff))
                uid = 'trending-tag:%s' % tag.name
                try:
                    last_insight = Insight.objects.filter(community=community, uid=uid).order_by('-timestamp')[0]
                    days_since_last_insight = (datetime.datetime.utcnow() - last_insight.timestamp).days
                    if days_since_last_insight < offset_days:
                        return
                except:
                    pass
                insight_title = '%s is trending' % tag.name
                insight_text = '<p>Over the past %s days there has been an increase is conversations tagged with <span class="tag-pill text-nowrap" style="background-color: #%s; "><span class="tag-text" style="color: #%saa;">%s</span></span>.</p>' % (offset_days, tag.color, tag.color, tag.name)
                insight_text += '<p>There has been a %0.2f%% increase over previous %s days, and a %0.2f%% increase over the %s days prior to that.<p>' % (baseline_diff, offset_days, trend_diff, trend_days)
                Insight.create(
                    community=community, 
                    recipient=community.managers or community.owner,
                    uid=uid,
                    level=Insight.InsightLevel.INFO,
                    title=insight_title,
                    text=insight_text,
                    cta="View Conversations",
                    link=reverse('conversations', kwargs={'community_id':community.id})+"?clear=all&timespan=90&tag=%s"%tag.name
                )

    def make_level_insights(self, community):
        offset_days = 30
        try:
            last_insight = Insight.objects.filter(community=community, uid='new-core-members').order_by('-timestamp')[0]
            days_since_last_insight = (datetime.datetime.utcnow() - last_insight.timestamp).days
            if days_since_last_insight < offset_days:
                return
        except:
            pass

        default_project, created = Project.objects.get_or_create(community=community, default_project=True, defaults={'name': community.name, 'owner':None, 'threshold_user':1, 'threshold_participant':10, 'threshold_contributor':1, 'threshold_core':10})
        current_core = [r[0] for r in MemberLevel.objects.filter(community=community, project=default_project, level=MemberLevel.CORE).values_list('member_id')]
        new_core_members = set()
        source_counts = dict()
        type_counts = dict()
        
        author_filter = Q(contribution__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period + offset_days), contribution__timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=offset_days))
        for member in Member.objects.filter(community=community).annotate(contrib_count=Count('contribution__id', filter=author_filter, distinct=True), last_contrib=Max('contribution__timestamp', filter=author_filter)):
            if member.contrib_count >= default_project.threshold_contributor and member.contrib_count < default_project.threshold_core:
                if member.id in current_core and member.role == Member.COMMUNITY:
                    new_core_members.add(member)
                    last_contrib = member.contribution_set.prefetch_related('channel__source').order_by('-timestamp')[0]
                    last_source = last_contrib.channel.source
                    if last_source not in source_counts:
                        source_counts[last_source] = 1
                    else:
                        source_counts[last_source] += 1
                    if last_contrib.contribution_type not in type_counts:
                        type_counts[last_contrib.contribution_type] = 1
                    else:
                        type_counts[last_contrib.contribution_type] += 1

        if len(new_core_members) > 0:
            insight_text = "<div class=\"row\"><div class=\"col-12 col-lg-6\">The following members of your community have just been promoted to the Core engagement level:<ul>"
            for member in new_core_members:
                insight_text += "<li><a href=\"%s\">%s</a></li>\n" % (reverse('member_profile', kwargs={'member_id':member.id}), member.name)
            insight_text += "</ul></div><div class=\"col-12 col-lg-6\">The most recent sources of their contributions are:<ul>"
            for source, count in source_counts.items():
                insight_text += "<li><a href=\"%s?clear=all&source=%s\">%s</a>: %s</li>" % (reverse('contributions', kwargs={'community_id':community.id}), source.id, source.connector_name, count)
            insight_text += "</ul>The most recent types of contributions were:<ul>"
            for contrib_type, count in type_counts.items():
                insight_text += "<li><a href=\"%s?clear=all&type=%s\">%s</a>: %s</li>" % (reverse('contributions', kwargs={'community_id':community.id}), contrib_type.name, contrib_type.name, count)
            insight_text += "</ul></div></div>"

            Insight.create(
                community=community, 
                recipient=community.managers or community.owner,
                uid='new-core-members',
                level=Insight.InsightLevel.SUCCESS,
                title='You have new <b>Core</b> community members!',
                text=insight_text,
            )

    def make_source_insights(self, community):
        trigger_days = 3
        trigger_messages = 10
        channels = Channel.objects.filter(source__community=community)
        channels = channels.annotate(last_community_msg=Max('conversation__timestamp', filter=Q(conversation__speaker__role=Member.COMMUNITY)))
        channels = channels.annotate(last_staff_msg=Max('conversation__timestamp', filter=Q(conversation__speaker__role=Member.STAFF)))
        channels = channels.annotate(newer_community_msgs=Count('conversation', filter=Q(conversation__speaker__role=Member.COMMUNITY, conversation__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=trigger_days))))
        channels = channels.filter(last_staff_msg__lte=datetime.datetime.utcnow() - datetime.timedelta(days=trigger_days))
        channels = channels.filter(newer_community_msgs__gte=trigger_messages)
        channels = channels.order_by(Lower('source__name'))
        for channel in channels:
            print("[%s] %s > %s: %s since %s" % (channel.source.connector_name, channel.source.name, channel.name, channel.newer_community_msgs, channel.last_staff_msg))
            uid = 'channel-neglect:%s:%s' % (channel.id, channel.last_staff_msg)
            insight_text = '<p>There have been %s comments in <b>%s</b> on <b>%s</b> (%s) since the last staff comment on %s.</p>' % (channel.newer_community_msgs, channel.name, channel.source.name, channel.source.connector_name, channel.last_staff_msg.strftime("%a %B %d %Y"))
            channel_url = channel.get_origin_url()

            try:
                last_insight = Insight.objects.filter(community=community, uid=uid).order_by('-timestamp')[0]
                days_since_last_insight = (datetime.datetime.utcnow() - last_insight.timestamp).days
                if days_since_last_insight < trigger_days:
                    return
            except:
                pass
            Insight.create(
                community=community, 
                recipient=community.managers or community.owner,
                uid=uid,
                level=Insight.InsightLevel.WARNING,
                title="Channel <b>%s</b> on <b>%s</b> needs staff attention" % (channel.name, channel.source.connector_name),
                text=insight_text,
                cta="View Channel",
                link=channel_url
            )

    def make_first_contrib(self, community):
        offset_days = 1
        new_since = datetime.datetime.utcnow() - datetime.timedelta(days=offset_days)
        uid = 'new-contributor-members'
        try:
            last_insight = Insight.objects.filter(community=community, uid=uid).order_by('-timestamp')[0]
            if last_insight.timestamp > new_since:
                return
            new_since = last_insight.timestamp
            offset_days = (datetime.datetime.utcnow() - new_since).days
        except:
            pass
        members = Member.objects.filter(community=community)
        members = members.annotate(first_contrib=Min('contribution__timestamp'))
        members = members.filter(first_contrib__gte=new_since)

        print("New contributors: %s" % members.count())
        if members.count() < 1:
            return
        source_counts = dict()
        type_counts = dict()
        tag_counts = dict()
        oldest_contrib = None
        insight_title = 'You have <b>%s</b> new Contributors!' % members.count()
        insight_text = "<div class=\"row\"><div class=\"col-12 col-lg-6\">The following members of your community have just made their first contribution:<ul>"
        for member in members:
            insight_text += "<li><a href=\"%s\">%s</a></li>\n" % (reverse('member_profile', kwargs={'member_id':member.id}), member.name)
            first_contrib = member.contribution_set.all().order_by('timestamp')[0]
            if first_contrib.channel.source not in source_counts:
                source_counts[first_contrib.channel.source] = 1
            else:
                source_counts[first_contrib.channel.source] += 1
            if first_contrib.contribution_type not in type_counts:
                type_counts[first_contrib.contribution_type] = 1
            else:
                type_counts[first_contrib.contribution_type] += 1
            for tag in first_contrib.tags.all():
                if tag not in tag_counts:
                    tag_counts[tag] = 1
                else:
                    tag_counts[tag] += 1
            if oldest_contrib is None or oldest_contrib > first_contrib.timestamp:
                oldest_contrib = first_contrib.timestamp
        insight_text += "</ul></div><div class=\"col-12 col-lg-6\">The sources of their contributions are:<ul>"
        for source, count in source_counts.items():
            insight_text += "<li><a href=\"%s?clear=all&source=%s\">%s</a>: %s</li>" % (reverse('contributions', kwargs={'community_id':community.id}), source.id, source.connector_name, count)
        insight_text += "</ul>The most recent types of contributions were:<ul>"
        for contrib_type, count in type_counts.items():
            insight_text += "<li><a href=\"%s?clear=all&type=%s\">%s</a>: %s</li>" % (reverse('contributions', kwargs={'community_id':community.id}), contrib_type.name, contrib_type.name, count)
        insight_text += "</ul></div></div>"

        if len(tag_counts) > 0:
            insight_text += "<p>Their primary topics were:<ul>"
            for tag, count in sorted(tag_counts.items(), key=lambda item: item[1]):
                insight_text += '<li><span class="tag-pill text-nowrap" style="background-color: #%s; "><span class="tag-text" style="color: #%saa;">%s</span></span> (%s contributions)</li>' % (tag.color, tag.color, tag.name, count)
            insight_text += "</ul></p>"
        timespan = datetime.datetime.utcnow() - oldest_contrib
        print("Creating insight for %s new contributors" % members.count())

        Insight.create(
            community=community, 
            recipient=community.managers or community.owner,
            uid=uid,
            level=Insight.InsightLevel.SUCCESS,
            title=insight_title,
            text=insight_text,
            cta="View Members",
            link=reverse('contributors', kwargs={'community_id':community.id})+"?clear=all&sort=-first_contrib"
        )