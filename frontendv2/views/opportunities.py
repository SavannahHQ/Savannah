import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.db.models.functions import Trunc, Lower
from django.contrib import messages
from django.http import JsonResponse
from django import forms
from django.core.exceptions import ValidationError

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import FunnelChart, PieChart, ChartColors
from corm import colors

class Opportunities(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "opportunities"
        self.charts = set()
        self._funnelChart = None
        self._winRateChart = None
        self._typeChart = None
        self.filter.update({
            'timespan': True,
            'custom_timespan': True,
            'member': True,
            'tag': False,
            'source': True,
            'contrib_type': True,
        })

    @property
    def all_opportunities(self):
        opps = Opportunity.objects.filter(community=self.community)
        opps = opps.filter(created_at__gte=self.rangestart, created_at__lte=self.rangeend)
        if self.member_company:
            opps = opps.filter(member__company=self.member_company)
        if self.member_tag:
            opps = opps.filter(member__tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                opps = opps.exclude(member__role=self.role)
            else:
                opps = opps.filter(member__role=self.role)
        if self.source:
            opps = opps.filter(source=self.source)
        if self.contrib_type:
            opps = opps.filter(contribution_type__name=self.contrib_type)
        opps = opps.order_by('-deadline')
        return opps

    @property
    def funnel_chart(self):
        if self._funnelChart is None:
            statuses = Opportunity.STATUS_CHOICES[2:]
            status_colors = colors.OPPORTUNITY.colors[2:]
            self._funnelChart = FunnelChart('opps_funnel', 'Opportunity Funnel', stages=statuses, colors=ChartColors(status_colors), invert=False)
            for status, name in statuses:
                opps = Opportunity.objects.filter(community=self.community, status=status)
                opps = opps.filter(created_at__gte=self.rangestart, created_at__lte=self.rangeend)
                if self.member_company:
                    opps = opps.filter(member__company=self.member_company)
                if self.member_tag:
                    opps = opps.filter(member__tags=self.member_tag)
                if self.role:
                    if self.role == Member.BOT:
                        opps = opps.exclude(member__role=self.role)
                    else:
                        opps = opps.filter(member__role=self.role)
                if self.source:
                    opps = opps.filter(source=self.source)
                if self.contrib_type:
                    opps = opps.filter(contribution_type__name=self.contrib_type)
                self._funnelChart.add(status, opps.count())
            self.charts.add(self._funnelChart)
        return self._funnelChart

    @property
    def win_rate(self):
        if self._winRateChart is None:
            self._winRateChart = PieChart("winrateChart", title="Closed Status")
            color_map = {
                Opportunity.COMPLETE: colors.OPPORTUNITY.COMPLETE,
                Opportunity.DECLINED: colors.OPPORTUNITY.DECLINED,
                Opportunity.REJECTED: colors.OPPORTUNITY.REJECTED,
            }
            opps = Opportunity.objects.filter(community=self.community, status__in=[Opportunity.COMPLETE, Opportunity.DECLINED, Opportunity.REJECTED])
            opps = opps.filter(created_at__gte=self.rangestart, created_at__lte=self.rangeend)
            if self.member_company:
                opps = opps.filter(member__company=self.member_company)
            if self.member_tag:
                opps = opps.filter(member__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    opps = opps.exclude(member__role=self.role)
                else:
                    opps = opps.filter(member__role=self.role)
            if self.source:
                opps = opps.filter(source=self.source)
            if self.contrib_type:
                opps = opps.filter(contribution_type__name=self.contrib_type)
            counts = opps.values('status').annotate(count=Count('id')).order_by('-status')
            for status in counts:
                if status['count'] > 0:
                    self._winRateChart.add(Opportunity.STATUS_MAP[status['status']], status['count'], color_map[status['status']])
            self.charts.add(self._winRateChart)
        return self._winRateChart

    @property
    def contrib_types(self):
        if self._typeChart is None:
            self._typeChart = PieChart("contribTypeChart", title="By Contribution Type")
            opps = Opportunity.objects.filter(community=self.community, status__gte=Opportunity.IDENTIFIED)
            opps = opps.filter(created_at__gte=self.rangestart, created_at__lte=self.rangeend)
            if self.member_company:
                opps = opps.filter(member__company=self.member_company)
            if self.member_tag:
                opps = opps.filter(member__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    opps = opps.exclude(member__role=self.role)
                else:
                    opps = opps.filter(member__role=self.role)
            if self.source:
                opps = opps.filter(source=self.source)
            if self.contrib_type:
                opps = opps.filter(contribution_type__name=self.contrib_type)
            counts = opps.values('contribution_type__name').annotate(count=Count('id')).order_by('-count')
            for status in counts:
                if status['count'] > 0:
                    self._typeChart.add(status['contribution_type__name'], status['count'])
            self.charts.add(self._typeChart)
        return self._typeChart

    @login_required
    def as_view(request, community_id):
        overview = Opportunities(request, community_id)

        return render(request, 'savannahv2/opportunities.html', overview.context)

    @login_required
    def update_opportunity(request, community_id):
        if request.method == "POST":
            try:
                opp_id, status = request.POST.get('move_to').split(':')
                opp_id = int(opp_id)
                status = int(status)
            except:
                messages.error(request, 'Bad opportunity or status, can not update.')
                return redirect('opportunities', community_id=community_id)
            try:
                opp = Opportunity.objects.get(id=opp_id, community_id=community_id)
                opp.status = status
                if opp.status in Opportunity.CLOSED_STATUSES:
                    if opp.closed_at is None:
                        opp.closed_at = datetime.datetime.utcnow()
                    if opp.closed_by is None:
                        opp.closed_by = request.user
                else:
                    opp.closed_at = None
                    opp.closed_by = None
                opp.save()
                messages.success(request, "Opportunity status updated to %s." % opp.get_status_display())
            except:
                messages.error(request, "Opportunity not found, can not update its status.")
        return redirect('opportunities', community_id=community_id)


class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ['member', 'name', 'contribution_type', 'status', 'deadline', 'description']
        widgets = {
            'deadline': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }

    def limit(self):
        community = self.instance.community
        if hasattr(self.instance, 'member'):
            self.fields['member'].widget.choices = [(self.instance.member.id, self.instance.member.name)]
        else:
            self.fields['member'].widget.choices = [('', '-----')]
            
        current_source = None
        choices = [('', '-----')]
        for contrib_type in ContributionType.objects.filter(community=community, source__isnull=False).select_related('source').order_by(Lower('source__connector')):
            source_name = '%s (%s)' % (contrib_type.source.connector_name, contrib_type.source.name)
            if source_name != current_source:
                current_source = source_name
                choices.append((source_name, []))
            choices[-1][1].append((contrib_type.id, contrib_type.name))
        self.fields['contribution_type'].widget.choices = choices

class AddOpportunity(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "opportunities"
        self.opportunity = Opportunity(community=self.community, created_by=request.user, deadline=datetime.datetime.utcnow() + datetime.timedelta(days=7))
        self.back_url = reverse('opportunities', kwargs={'community_id':community_id})
        self.self_url = reverse('opportunity_add', kwargs={'community_id':community_id})

    def form(self, data=None):
        self._form = OpportunityForm(instance=self.opportunity, data=data)
        self._form.limit()
        return self._form

    def as_view(request, community_id):
        view = AddOpportunity(request, community_id)

        if request.method == 'POST':
            form = view.form(request.POST)
            if form.is_valid():
                opp = form.save(commit=False)
                opp.source = opp.contribution_type.source
                if opp.status in Opportunity.CLOSED_STATUSES:
                    if opp.closed_at is None:
                        opp.closed_at = datetime.datetime.utcnow()
                    if opp.closed_by is None:
                        opp.closed_by = request.user
                else:
                    opp.closed_at = None
                    opp.closed_by = None
                opp.save()

                messages.success(request, 'Opportunity has been added')
                return redirect('opportunities', community_id=view.community.id)
        return render(request, 'savannahv2/opportunity_add.html', view.context)

class EditOpportunity(SavannahView):
    def __init__(self, request, community_id, opp_id):
        super().__init__(request, community_id)
        self.active_tab = "opportunities"
        self.opportunity = get_object_or_404(Opportunity, id=opp_id, community=self.community)
        self.back_url = reverse('opportunities', kwargs={'community_id':community_id})
        self.self_url = reverse('opportunity_edit', kwargs={'community_id':community_id, 'opp_id':opp_id})

    def form(self, data=None):
        self._form = OpportunityForm(instance=self.opportunity, data=data)
        self._form.limit()
        return self._form

    def as_view(request, community_id, opp_id):
        view = EditOpportunity(request, community_id, opp_id)

        if request.method == 'POST':
            form = view.form(request.POST)
            if form.is_valid():
                opp = form.save(commit=False)
                opp.source = opp.contribution_type.source
                if opp.status in Opportunity.CLOSED_STATUSES:
                    if opp.closed_at is None:
                        opp.closed_at = datetime.datetime.utcnow()
                    if opp.closed_by is None:
                        opp.closed_by = request.user
                else:
                    opp.closed_at = None
                    opp.closed_by = None
                opp.save()

                messages.success(request, 'Opportunity has been updated')
                return redirect('opportunities', community_id=view.community.id)
        return render(request, 'savannahv2/opportunity_edit.html', view.context)