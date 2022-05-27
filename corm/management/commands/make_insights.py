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
            self.make_level_insights(community=community)

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
                title='You have new Core community members!',
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
