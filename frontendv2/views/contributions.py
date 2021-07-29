import operator
import datetime
import csv
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, Min
from django.db.models.functions import Lower
from django.utils.safestring import mark_safe

from corm.models import *
from frontendv2.views import SavannahFilterView
from frontendv2.views.charts import PieChart
from frontendv2.models import PublicDashboard

class Contributions(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "contributions"
        self._membersChart = None
        self._channelsChart = None

        self.filter.update({
            'timespan': True,
            'custom_timespan': True,
            'member': True,
            'tag': True,
            'source': True,
            'contrib_type': True,
        })

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

    def suggestion_count(self):
        return SuggestConversationAsContribution.objects.filter(community=self.community, status__isnull=True).count()

    @property
    def all_contributions(self):
        contributions = Contribution.objects.filter(community=self.community)
        contributions = contributions.filter(timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
        if self.contrib_type:
            contributions = contributions.filter(contribution_type__name=self.contrib_type)

        if self.tag:
            contributions = contributions.filter(tags=self.tag)

        if self.member_company:
            contributions = contributions.filter(author__company=self.member_company)

        if self.member_tag:
            contributions = contributions.filter(author__tags=self.member_tag)

        if self.role:
            if self.role == Member.BOT:
                contributions = contributions.exclude(author__role=self.role)
            else:
                contributions = contributions.filter(author__role=self.role)

        if self.source:
            contributions = contributions.filter(channel__source=self.source)

        contributions = contributions.annotate(author_name=F('author__name'), channel_name=F('channel__name'), source_name=F('contribution_type__source__name'), source_icon=F('contribution_type__source__icon_name')).prefetch_related('tags').order_by('-timestamp')
        self.result_count = contributions.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return contributions[start:start+self.RESULTS_PER_PAGE]

    @property
    def page_start(self):
        return ((self.page-1) * self.RESULTS_PER_PAGE) + 1

    @property
    def page_end(self):
        end = ((self.page-1) * self.RESULTS_PER_PAGE) + self.RESULTS_PER_PAGE
        if end > self.result_count:
            return self.result_count
        else:
            return end

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        return pages

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        offset=1
        if self.page > 5:
            offset = self.page - 5
        if offset + 9 > pages:
            offset = pages - 9
        if offset < 1:
            offset = 1
        return [page+offset for page in range(min(10, pages))]

    @property
    def new_contributors(self):
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q()
        if self.contrib_type:
            contrib_filter = contrib_filter &Q(contribution__contribution_type__name=self.contrib_type)
        if self.tag:
            contrib_filter = contrib_filter &Q(contribution__tags=self.tag)
        if self.source:
            contrib_filter = contrib_filter &Q(contribution__channel__source=self.source)

        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)

        members = members.annotate(first_contrib=Min('contribution__timestamp', filter=contrib_filter))
        members = members.filter(first_contrib__gte=self.rangestart, first_contrib__lte=self.rangeend)
        members = members.prefetch_related('tags')
        actives = dict()
        for m in members:
            if m.first_contrib is not None:
                actives[m] = m.first_contrib
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def recent_contributors(self):
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__gte=self.rangestart, contribution__timestamp__lte=self.rangeend)
        if self.contrib_type:
            contrib_filter = contrib_filter & Q(contribution__contribution_type__name=self.contrib_type)
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.source:
            contrib_filter = contrib_filter &Q(contribution__channel__source=self.source)

        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)

        members = members.annotate(last_active=Max('contribution__timestamp', filter=contrib_filter)).filter(last_active__isnull=False).prefetch_related('tags')
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
        contrib_filter = Q(contribution__timestamp__gte=self.rangestart, contribution__timestamp__lte=self.rangeend)
        if self.contrib_type:
            contrib_filter = contrib_filter & Q(contribution__contribution_type__name=self.contrib_type)
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.source:
            contrib_filter = contrib_filter &Q(contribution__channel__source=self.source)

        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)

        members = members.annotate(contribution_count=Count('contribution', filter=contrib_filter)).filter(contribution_count__gt=0).prefetch_related('tags')
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
        contrib_filter = Q(contribution__timestamp__gte=self.rangestart, contribution__timestamp__lte=self.rangeend)
        if self.contrib_type:
            contrib_filter = contrib_filter & Q(contribution__contribution_type__name=self.contrib_type)
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.source:
            contrib_filter = contrib_filter &Q(contribution__channel__source=self.source)

        if self.member_company:
            contributors = contributors.filter(company=self.member_company)
        if self.member_tag:
            contributors = contributors.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                contributors = contributors.exclude(role=self.role)
            else:
                contributors = contributors.filter(role=self.role)

        contributors = contributors.annotate(contribution_count=Count('contribution', filter=contrib_filter))
        contributors = contributors.filter(contribution_count__gt=0).order_by('-contribution_count')
        for c in contributors:
            contributor_ids.add(c.id)

        members = Member.objects.filter(community=self.community)
        members = members.annotate(conversation_count=Count('initiator_of', filter=Q(initiator_of__member__in=contributor_ids, initiator_of__timestamp__gte=self.rangestart, initiator_of__timestamp__lte=self.rangeend)))
        members = members.order_by('-conversation_count').filter(conversation_count__gt=0).prefetch_related('tags')
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
        contrib_filter = Q(contribution__timestamp__gte=self.rangestart, contribution__timestamp__lte=self.rangeend)
        if self.contrib_type:
            contrib_filter = contrib_filter & Q(contribution__contribution_type__name=self.contrib_type)
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
        if self.source:
            contrib_filter = contrib_filter &Q(contribution__channel__source=self.source)

        if self.member_company:
            contributors = contributors.filter(company=self.member_company)
        if self.member_tag:
            contributors = contributors.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                contributors = contributors.exclude(role=self.role)
            else:
                contributors = contributors.filter(role=self.role)

        contributors = contributors.annotate(contribution_count=Count('contribution', filter=contrib_filter)).filter(contribution_count__gt=0)

        for c in contributors:
            if c.contribution_count > 0:
                contributor_ids.add(c.id)

        members = Member.objects.filter(community=self.community)
        members = members.annotate(connection_count=Count('memberconnection__id', filter=Q(memberconnection__to_member__in=contributor_ids, memberconnection__first_connected__lte=self.rangeend, memberconnection__last_connected__gte=self.rangestart)))
        members = members.order_by('-connection_count').filter(connection_count__gt=0).prefetch_related('tags')
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

            contributions = Contribution.objects.filter(community=self.community, timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)

            if self.contrib_type:
                contributions = contributions.filter(contribution_type__name=self.contrib_type)

            if self.tag:
                contributions = contributions.filter(tags=self.tag)
            if self.source:
                contributions = contributions.filter(channel__source=self.source)

            if self.member_company:
                contributions = contributions.filter(author__company=self.member_company)
            if self.member_tag:
                contributions = contributions.filter(author__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    contributions = contributions.exclude(author__role=self.role)
                else:
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

    def channels_chart(self):
        if not self._channelsChart:
            channels = list()
            counts = dict()


            channels = Channel.objects.filter(source__community=self.community)
            contrib_filter = Q(contribution__timestamp__gte=self.rangestart, contribution__timestamp__lte=self.rangeend)
            if self.contrib_type:
                contrib_filter = contrib_filter & Q(contribution__contribution_type__name=self.contrib_type)
            if self.tag:
                contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
            if self.source:
                contrib_filter = contrib_filter & Q(contribution__channel__source=self.source)
            if self.member_company:
                contrib_filter = contrib_filter & Q(contribution__author__company=self.member_company)
            if self.member_tag:
                contrib_filter = contrib_filter & Q(contribution__author__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    contrib_filter = contrib_filter & ~Q(contribution__author__role=self.role)
                else:
                    contrib_filter = contrib_filter & Q(contribution__author__role=self.role)

            channels = channels.annotate(contribution_count=Count('contribution', filter=contrib_filter))
            channels = channels.annotate(source_icon=F('source__icon_name'), source_connector=F('source__connector'), color=F('tag__color'))
            for c in channels:
                if c.contribution_count == 0:
                    continue
                counts[c] = c.contribution_count
            self._channelsChart = PieChart("channelsChart", title="Contributions by Channel", limit=8)
            for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                self._channelsChart.add("%s (%s)" % (channel.name, ConnectionManager.display_name(channel.source_connector)), count, channel.color)
        self.charts.add(self._channelsChart)
        return self._channelsChart

    @login_required
    def as_view(request, community_id):
        view = Contributions(request, community_id)
        return render(request, 'savannahv2/contributions.html', view.context)

    @login_required
    def publish(request, community_id):
        if 'cancel' in request.GET:
            return redirect('contributions', community_id=community_id)
            
        contributions = Contributions(request, community_id)
        return contributions.publish_view(request, PublicDashboard.CONTRIBUTIONS, 'public_contributions')

    def public(request, dashboard_id):
        dashboard = get_object_or_404(PublicDashboard, id=dashboard_id)
        contributions = Contributions(request, dashboard.community.id)
        context = dashboard.apply(contributions)
        if not request.user.is_authenticated:
            dashboard.count()
        return render(request, 'savannahv2/public/contributions.html', context)

class Contributors(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "contributions"
        self.sort_by = request.session.get("sort_contributors", "name")
        self.filter.update({
            'timespan': True,
            'custom_timespan': True,
            'member': True,
            'member_role': True,
            'member_tag': True,
            'member_company': True,
            'tag': True,
            'source': True,
            'contrib_type': True,
        })

        self.RESULTS_PER_PAGE = 25

        if 'sort' in request.GET and request.GET.get('sort') in ('name', '-name', 'company', '-company', 'first_contrib', '-first_contrib', 'last_contrib', '-last_contrib', 'contrib_count', '-contrib_count'):
            self.sort_by = request.GET.get('sort') 
            request.session['sort_contributors'] = self.sort_by

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
    def all_contributors(self):
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q()
        contrib_range_filter = Q(contribution__timestamp__gte=self.rangestart, contribution__timestamp__lte=self.rangeend)
        if self.contrib_type:
            contrib_filter = contrib_filter & Q(contribution__contribution_type__name=self.contrib_type)
            contrib_range_filter = contrib_range_filter & contrib_filter
        if self.tag:
            contrib_filter = contrib_filter & Q(contribution__tags=self.tag)
            contrib_range_filter = contrib_range_filter & contrib_filter
        if self.source:
            contrib_filter = contrib_filter &Q(contribution__channel__source=self.source)
            contrib_range_filter = contrib_range_filter & contrib_filter
        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)

        members = members.annotate(first_contrib=Min('contribution__timestamp', filter=contrib_filter))
        members = members.annotate(last_contrib=Max('contribution__timestamp', filter=contrib_range_filter))
        members = members.annotate(contrib_count=Count('contribution', filter=contrib_range_filter))
        members = members.prefetch_related('tags').select_related('company')
        if self.sort_by == 'name':
            members = members.order_by(Lower('name'))
        elif self.sort_by == '-name':
            members = members.order_by(Lower('name').desc())
        elif self.sort_by == 'company':
            members = members.order_by(Lower('company__name').asc(nulls_last=True))
        elif self.sort_by == '-company':
            members = members.order_by(Lower('company__name').desc(nulls_last=True))
        else:
            members = members.order_by(self.sort_by)

        return members

    @property
    def paged_contributors(self):
        members = self.all_contributors
        members = members.filter(last_contrib__isnull=False, first_contrib__isnull=False)
        members = members.prefetch_related('tags')
        
        self.result_count = members.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return members[start:start+self.RESULTS_PER_PAGE]

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        return pages

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)+1
        offset=1
        if self.page > 5:
            offset = self.page - 5
        if offset + 9 > pages:
            offset = pages - 9
        if offset < 1:
            offset = 1
        return [page+offset for page in range(min(10, pages))]

    @login_required
    def as_view(request, community_id):
        view = Contributors(request, community_id)
        return render(request, 'savannahv2/contributors.html', view.context)

    @login_required
    def as_csv(request, community_id):
        view = Contributors(request, community_id)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="contributors.csv"'
        writer = csv.DictWriter(response, fieldnames=['Member', 'Company', 'First Contrib', 'Last Contrib', 'Contrib Count', 'Tags'])
        writer.writeheader()
        for member in view.all_contributors:
            company_name = ''
            if member.company:
                company_name = member.company.name
            writer.writerow({
                'Member': member.name, 
                'Company':company_name, 
                'First Contrib':member.first_contrib, 
                'Last Contrib':member.last_contrib, 
                'Contrib Count':member.contrib_count,
                'Tags': ",".join([tag.name for tag in member.tags.all()])
            })
        return response