import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe

from corm.models import *
from frontendv2.views import SavannahFilterView

class Contributions(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "contributions"
        self._membersChart = None
        self._channelsChart = None

        self.RESULTS_PER_PAGE = 25

        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'search' in request.GET:
            self.search = request.GET.get('search', "").lower()
        else:
            self.search = None
        self.result_count = 0

    @property
    def all_contributions(self):
        contributions = Contribution.objects.filter(community=self.community)
        if self.tag:
            contributions = contributions.filter(tags=self.tag)

        if self.role:
            contributions = contributions.filter(author__role=self.role)

        contributions = contributions.annotate(author_name=F('author__name'), tag_count=Count('tags'), channel_name=F('channel__name'), source_name=F('contribution_type__source__name'), source_icon=F('contribution_type__source__icon_name')).order_by('-timestamp')
        self.result_count = contributions.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return contributions[start:start+self.RESULTS_PER_PAGE]

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return min(10, pages+1)

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return [page+1 for page in range(min(10, pages+1))]

    @property
    def recent_contributors(self):
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__isnull=False)
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)

        members = members.annotate(last_active=Max('contribution__timestamp', filter=contrib_filter))
        actives = dict()
        for m in members:
            if m.last_active is not None:
                actives[m] = m.last_active
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def top_contributors(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)

        members = members.annotate(contribution_count=Count('contribution', filter=contrib_filter))
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
        contributors = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.role:
            contributors = contributors.filter(role=self.role)

        contributors = contributors.annotate(contribution_count=Count('contribution', filter=contrib_filter))
        contributors = contributors.filter(contribution_count__gt=0).order_by('-contribution_count')
        for c in contributors:
            if c.contribution_count > 0:
                contributor_ids.add(c.id)

        members = Member.objects.filter(community=self.community)
        members = members.annotate(conversation_count=Count('speaker_in', filter=Q(speaker_in__participants__in=contributor_ids, speaker_in__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
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
        contributors = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.role:
            contributors = contributors.filter(role=self.role)

        contributors = contributors.annotate(contribution_count=Count('contribution', filter=contrib_filter))

        for c in contributors:
            if c.contribution_count > 0:
                contributor_ids.add(c.id)

        members = Member.objects.filter(community=self.community)
        members = members.annotate(connection_count=Count('memberconnection__id', filter=Q(memberconnection__to_member__in=contributor_ids, memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
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

            contributions = Contribution.objects.filter(community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if self.tag:
                contributions = contributions.filter(tags=self.tag)

            if self.role:
                contributions = contributions.filter(author__role=self.role)
            contributions = contributions.order_by("timestamp")

            for m in contributions:
                month = self.trunc_date(m.timestamp)
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
        return self.timespan_chart_keys(months)

    @property
    def contributions_chart_counts(self):
        (months, counts) = self.getContributionsChart()
        return [counts.get(month, 0) for month in self.timespan_chart_keys(months)]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            from_colors = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc', 'ffa280']
            next_color = 0

            channels = Channel.objects.filter(source__community=self.community)
            contrib_filter = Q(contribution__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if self.tag:
                contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
            if self.role:
                contrib_filter = contrib_filter & Q(contribution__author__role=self.role)

            channels = channels.annotate(contribution_count=Count('contribution', filter=contrib_filter))
            channels = channels.annotate(source_icon=F('source__icon_name'), source_connector=F('source__connector'), color=F('tag__color'))
            for c in channels:
                if c.contribution_count == 0:
                    continue
                if not c.color:
                    c.color = from_colors[next_color]
                    next_color += 1
                    if next_color >= len(from_colors):
                        next_color = 0    
                counts[c] = c.contribution_count
            self._channelsChart = [("%s (%s)" % (channel.name, ConnectionManager.display_name(channel.source_connector)), count, channel.color) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 7:
                other_count = sum([count for channel, count, colors in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:6]
                self._channelsChart.append(("Other", other_count, 'dfdfdf'))
            channelless = Contribution.objects.filter(community=self.community, channel__isnull=True)
            if self.tag:
                channelless = channelless.filter(tags=self.tag)
            if self.role:
                channelless = channelless.filter(author__role=self.role)

            self._channelsChart.append(("No Channel", channelless.count(), 'efefef'))
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
    def as_view(request, community_id):
        view = Contributions(request, community_id)
        return render(request, 'savannahv2/contributions.html', view.context)
