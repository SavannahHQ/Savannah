import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe

from corm.models import *

class Contributions:
    def __init__(self, community_id, tag=None, member_tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._channelsChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None
        if member_tag:
            self.member_tag = get_object_or_404(Tag, name=member_tag)
        else:
            self.member_tag = None

    @property
    def all_contributions(self):
        contributions = Contribution.objects.filter(community=self.community)
        if self.tag:
            contributions = contributions.filter(tags=self.tag)

        if self.member_tag:
            contributions = contributions.filter(author__tags=self.member_tag)

        contributions = contributions.annotate(author_name=F('author__name'), tag_count=Count('tags'), channel_name=F('channel__name'), source_name=F('contribution_type__source__name'), source_icon=F('contribution_type__source__icon_name')).order_by('-timestamp')
        return contributions[:100]

    @property
    def recent_contributors(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(last_active=Max('contribution__timestamp', filter=Q(contribution__timestamp__isnull=False, contribution__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(last_active=Max('contribution__timestamp', filter=Q(contribution__timestamp__isnull=False)))
        actives = dict()
        for m in members:
            if m.last_active is not None:
                actives[m] = m.last_active
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def top_contributors(self):
        activity_counts = dict()
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=182), contribution__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=182))))
        for m in members:
            if m.contribution_count > 0:
                activity_counts[m] = m.contribution_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def top_supporters(self):
        activity_counts = dict()
        contributor_ids = set()
        if self.tag:
            contributors = Member.objects.filter(community=self.community).annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30), contribution__tags=self.tag)))
        else:
            contributors = Member.objects.filter(community=self.community).annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
        contributors = contributors.filter(contribution_count__gt=0).order_by('-contribution_count')
        for c in contributors:
            if c.contribution_count > 0:
                contributor_ids.add(c.id)

        members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__participants__in=contributor_ids, conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
        members = members.order_by('-conversation_count')
        for m in members[:10]:
            if m.conversation_count > 0:
                activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]
  
    @property
    def top_enablers(self):
        activity_counts = dict()
        contributor_ids = set()
        if self.tag:
            contributors = Member.objects.filter(community=self.community).annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30), contribution__tags=self.tag)))
        else:
            contributors = Member.objects.filter(community=self.community).annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))))

        for c in contributors:
            if c.contribution_count > 0:
                contributor_ids.add(c.id)

        members = Member.objects.filter(community=self.community).annotate(connection_count=Count('memberconnection__id', filter=Q(memberconnection__to_member__in=contributor_ids, memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
        members = members.order_by('-connection_count')
        for m in members:
            if m.connection_count > 0:
                activity_counts[m] = m.connection_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]
  
    def getContributionsChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            contributions = Contribution.objects.filter(community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))
            if self.tag:
                contributions = contributions.filter(tags=self.tag)

            if self.member_tag:
                contributions = contributions.filter(author__tags=self.member_tag)
            contributions = contributions.order_by("timestamp")

            for m in contributions:
                month = str(m.timestamp)[:10]
                if month not in months:
                    months.append(month)
                if month not in counts:
                    counts[month] = 1
                else:
                    counts[month] += 1
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def contributions_chart_months(self):
        (months, counts) = self.getContributionsChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(180)]
        date_list.reverse()
        return [str(day)[:10] for day in date_list]

    @property
    def contributions_chart_counts(self):
        (months, counts) = self.getContributionsChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(180)]
        date_list.reverse()
        return [counts.get(str(day)[:10], 0) for day in date_list]
        #return [counts[month] for month in months]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            colors = list()
            from_colors = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc', 'ffa280']
            next_color = 0

            total = 0
            channels = Channel.objects.filter(source__community=self.community)
            if self.tag:
                if self.member_tag:
                    channels = channels.annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), contribution__tags=self.tag, contribution__author__tags=self.member_tag)))
                else:
                    channels = channels.annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), contribution__tags=self.tag)))
            else:
                if self.member_tag:
                    channels = channels.annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), contribution__author__tags=self.member_tag)))
                else:
                    channels = channels.annotate(contribution_count=Count('contribution', filter=Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))))

            channels = channels.annotate(source_icon=F('source__icon_name'), color=F('tag__color'))
            for c in channels:
                if c.contribution_count == 0:
                    continue
                if not c.color:
                    c.color = from_colors[next_color]
                    next_color += 1
                    if next_color >= len(from_colors):
                        next_color = 0    
                counts[c] = c.contribution_count
            self._channelsChart = [(channel.name, count, channel.color) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 7:
                other_count = sum([count for channel, count, colors in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:6]
                self._channelsChart.append(("Other", other_count, 'dfdfdf'))
            if self.tag:
                if self.member_tag:
                    self._channelsChart.append(("No Channel", Contribution.objects.filter(community=self.community, channel__isnull=True, tags=self.tag, author__tags=self.tag).count(), 'efefef'))
                else:
                    self._channelsChart.append(("No Channel", Contribution.objects.filter(community=self.community, channel__isnull=True, tags=self.tag).count(), 'efefef'))
            else:
                if self.member_tag:
                    self._channelsChart.append(("No Channel", Contribution.objects.filter(community=self.community, channel__isnull=True, author__tags=self.tag).count(), 'efefef'))
                else:
                    self._channelsChart.append(("No Channel", Contribution.objects.filter(community=self.community, channel__isnull=True).count(), 'efefef'))
        return self._channelsChart

    @property
    def channel_names(self):
        chart = self.getChannelsChart()
        return mark_safe(str([channel[0] for channel in chart]))

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart]

    @property
    def channel_colors(self):
        chart = self.getChannelsChart()
        return ['#'+channel[2] for channel in chart]



@login_required
def contributions(request, community_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))
    request.session['community'] = community_id
    kwargs = dict()
    if 'tag' in request.GET:
        kwargs['tag'] = request.GET.get('tag')

    if 'member_tag' in request.GET:
        kwargs['member_tag'] = request.GET.get('member_tag')

    contributions = Contributions(community_id, **kwargs)
    try:
        user_member = Member.objects.get(user=request.user, community=contributions.community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": contributions.community,
        "active_tab": "contributions",
        "view": contributions,
    }
    return render(request, 'savannahv2/contributions.html', context)
