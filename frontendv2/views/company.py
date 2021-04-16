import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, Min
from django.db.models.functions import Trunc, Lower

from django.contrib import messages
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import PieChart, ChartColors

class CompanyProfile(SavannahView):
    def __init__(self, request, company_id):
        self.company = get_object_or_404(Company, id=company_id)
        super().__init__(request, self.company.community.id)
        self.active_tab = "company"
        self._sourcesChart = None
        self._engagementChart = None
        self._tagsChart = None
        self.timespan=366

        self.RESULTS_PER_PAGE = 25
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'conversation_search' in request.GET:
            self.conversation_search = request.GET.get('conversation_search', "").lower()
        else:
            self.conversation_search = None
        self.result_count = 0

    @property
    def all_members(self):
        members = Member.objects.filter(community=self.community, company=self.company)
        members = members.prefetch_related('tags')
        members = members.prefetch_related('collaborations')
        return members.order_by('-last_seen')

    @property
    def all_notes(self):
        return Note.objects.filter(member__company=self.company).select_related('member').order_by('-timestamp')

    @property
    def tagsChart(self):
        if not self._tagsChart:
            counts = dict()
            tags = Tag.objects.filter(community=self.community)
            convo_filter = Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            convo_filter = convo_filter & Q(conversation__speaker__company=self.company)

            tags = tags.annotate(conversation_count=Count('conversation', filter=convo_filter))
            tags = tags.filter(conversation_count__gt=0)

            for t in tags:
                counts[t] = t.conversation_count
            self._tagsChart = PieChart("tagsChart", title="Conversation Tags", limit=12)
            for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                if count > 0:
                    self._tagsChart.add(tag.name, count, tag.color)
        self.charts.add(self._tagsChart)
        return self._tagsChart

    @property
    def sourcesChart(self):
        if not self._sourcesChart:
            counts = dict()
            other_count = 0
            sources = Source.objects.filter(community=self.community)
            convo_filter = Q(channel__conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            convo_filter = convo_filter & Q(channel__conversation__speaker__company=self.company)

            sources = sources.annotate(conversation_count=Count('channel__conversation', filter=convo_filter))
            sources = sources.filter(conversation_count__gt=0)

            for s in sources:
                counts[s] = s.conversation_count

            self._sourcesChart = PieChart("sourcesChart", title="Converation Sources", limit=8)
            for source, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                self._sourcesChart.add("%s (%s)" % (source.name, ConnectionManager.display_name(source.connector)), count)
        self.charts.add(self._sourcesChart)
        return self._sourcesChart

    def getEngagementChart(self):
        if not self._engagementChart:
            conversations_counts = dict()
            activity_counts = dict()
            company_filter = Q(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))

            conversations = conversations = Conversation.objects.filter(channel__source__community=self.community, speaker__company=self.company)
            conversations = conversations.filter(company_filter)
            conversations = conversations.annotate(month=Trunc('timestamp', 'day')).values('month').annotate(convo_count=Count('id', distinct=True)).order_by('month')

            months = list()
            for c in conversations:
                month = str(c['month'])[:10]
                if month not in months:
                    months.append(month)
                conversations_counts[month] = c['convo_count']

            activity = Contribution.objects.filter(community=self.community, author__company=self.company)
            activity = activity.filter(company_filter)
            activity = activity.annotate(month=Trunc('timestamp', 'day')).values('month').annotate(contrib_count=Count('id', distinct=True)).order_by('month')

            for a in activity:
                month = str(a['month'])[:10]
                if month not in months:
                    months.append(month)
                activity_counts[month] = a['contrib_count']

            self._engagementChart = (conversations_counts, activity_counts)
        return self._engagementChart
        
    @property
    def engagement_chart_months(self):
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [str(day)[:10] for day in date_list]

    @property
    def engagement_chart_conversations(self):
        (conversations_counts, activity_counts) = self.getEngagementChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [conversations_counts.get(str(day)[:10], 0) for day in date_list]

    @property
    def engagement_chart_activities(self):
        (conversations_counts, activity_counts) = self.getEngagementChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [activity_counts.get(str(day)[:10], 0) for day in date_list]

    @property
    def all_conversations(self):
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        conversations = conversations.filter(participation__member__company=self.company)
        if self.conversation_search:
            conversations = conversations.filter(content__icontains=self.conversation_search)

        self.result_count = conversations.count()
        conversations = conversations.select_related('channel', 'channel__source', 'speaker').prefetch_related('tags').order_by('-timestamp')
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return conversations[start:start+self.RESULTS_PER_PAGE]

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
    def as_view(request, company_id):
        view = CompanyProfile(request, company_id)

        return render(request, "savannahv2/company.html", view.context)

class Companies(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "company"
        self._membersChart = None
        self._conversationsChart = None
        self._contributionsChart = None
        self._company_colors = dict()
        self.filter.update({
            'timespan': True,
            'custom_timespan': True,
            'member': False,
            'member_role': False,
            'member_tag': False,
            'member_company': False,
            'tag': True,
            'source': False,
            'conrib_type': False,
        })

    def suggestion_count(self):
        return SuggestCompanyCreation.objects.filter(community=self.community, status__isnull=True).count()

    def all_companies(self):
        companies = Company.objects.filter(community=self.community)
        if self.timefilter=='custom' or self.timespan < self.MAX_TIMESPAN:
            convo_filter = Q(member__speaker_in__timestamp__lte=self.rangeend, member__speaker_in__timestamp__gte=self.rangestart)
        else:
            convo_filter = Q()
        companies = companies.annotate(last_activity=Max('member__speaker_in__timestamp', filter=convo_filter))
        if self.timefilter=='custom' or self.timespan < self.MAX_TIMESPAN:
            companies = companies.filter(last_activity__isnull=False)
        if self.tag:
            companies = companies.filter(tag=self.tag)
        companies = companies.annotate(member_count=Count('member', distinct=True, filter=convo_filter))
        return companies.order_by(Lower('name'))

    def members_chart(self):
        if not self._membersChart:
            companies = Company.objects.filter(community=self.community, is_staff=False)
            convo_filter = Q(member__speaker_in__timestamp__lte=self.rangeend, member__speaker_in__timestamp__gte=self.rangestart)
            if self.tag:
                companies = companies.filter(tag=self.tag)
            companies = companies.annotate(member_count=Count('member', distinct=True, filter=convo_filter)).filter(member_count__gt=0).order_by('-member_count')

            chart_colors = ChartColors()
            self._membersChart = PieChart("membersChart", title="Members by Company")
            self._membersChart.set_show_legend(False)
            for company in companies:
                if company.tag:
                    self._company_colors[company.id] = company.tag.color
                else:
                    self._company_colors[company.id] = chart_colors.next()
                self._membersChart.add(company.name, company.member_count, data_color=self._company_colors[company.id], data_link=reverse('members', kwargs={'community_id': self.community.id})+"?member_company="+str(company.id))
        self.charts.add(self._membersChart)
        return self._membersChart

    def conversations_chart(self):
        if not self._conversationsChart:
            companies = Company.objects.filter(community=self.community, is_staff=False)
            convo_filter = Q(member__speaker_in__timestamp__lte=self.rangeend, member__speaker_in__timestamp__gte=self.rangestart)
            if self.tag:
                companies = companies.filter(tag=self.tag)
            companies = companies.annotate(convo_count=Count('member__speaker_in', filter=convo_filter)).filter(convo_count__gt=0).order_by('-convo_count')

            self._conversationsChart = PieChart("conversationsChart", title="Conversations by Company")
            self._conversationsChart.set_show_legend(False)
            for company in companies:
                self._conversationsChart.add(company.name, company.convo_count, data_color=self._company_colors[company.id], data_link=reverse('conversations', kwargs={'community_id': self.community.id})+"?member_company="+str(company.id))
        self.charts.add(self._conversationsChart)
        return self._conversationsChart

    def contributions_chart(self):
        if not self._contributionsChart:
            companies = Company.objects.filter(community=self.community, is_staff=False)
            contrib_filter = Q(member__contribution__timestamp__lte=self.rangeend, member__contribution__timestamp__gte=self.rangestart)
            if self.tag:
                companies = companies.filter(tag=self.tag)
            companies = companies.annotate(contrib_count=Count('member__contribution', filter=contrib_filter)).filter(contrib_count__gt=0).order_by('-contrib_count')

            chart_colors = ChartColors()
            self._contributionsChart = PieChart("contributionsChart", title="Contributions by Company")
            self._contributionsChart.set_show_legend(False)
            for company in companies:
                self._contributionsChart.add(company.name, company.contrib_count, data_color=self._company_colors.get(company.id, chart_colors.next()), data_link=reverse('contributions', kwargs={'community_id': self.community.id})+"?member_company="+str(company.id))
        self.charts.add(self._contributionsChart)
        return self._contributionsChart

    @login_required
    def as_view(request, community_id):
        view = Companies(request, community_id)
        if request.method == 'POST':
            if 'delete_company' in request.POST:
                company = get_object_or_404(Company, id=request.POST.get('delete_company'))
                context = view.context
                context.update({
                    'object_type':"the Company", 
                    'object_name': company.name, 
                    'object_id': company.id,
                    'warning_msg': "This will remove the Company from all Members",
                })
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                company = get_object_or_404(Company, id=request.POST.get('object_id'))
                company_name = company.name
                company.delete()
                messages.success(request, "Deleted company: <b>%s</b>" % company_name)

                return redirect('companies', community_id=community_id)

        return render(request, "savannahv2/companies.html", view.context)

class CompanyEditForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'website', 'domains', 'is_staff']
        
    domains = forms.CharField(required=False, help_text="Comma-separated list of email domains", label="Email Domains")
    def __init__(self, *args, **kwargs):
        super(CompanyEditForm, self).__init__(*args, **kwargs)
        if not 'domains' in self.initial:
            self.initial['domains'] = ', '.join([d.domain for d in CompanyDomains.objects.filter(company=self.instance)])

    def save(self, *args, **kwargs):
        saved = super(CompanyEditForm, self).save(*args, **kwargs)
        old_domains = dict([(d.domain, d) for d in CompanyDomains.objects.filter(company=self.instance)])
        new_domains = self.cleaned_data['domains'].split(',')
        for domain in new_domains:
            domain = domain.strip()
            if domain in old_domains:
                del old_domains[domain]
                continue
            else:
                CompanyDomains.objects.create(company=self.instance, domain=domain)

        for removed in old_domains.values():
            removed.delete()
        return saved

    def clean_domains(self):
        data = self.cleaned_data['domains']
        return data

class AddCompany(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.edit_company = Company(community=self.community)
        self.active_tab = "company"
        self.for_member = None
        self.default_name = None
        self.default_domain = None
        self.default_website = None

    @property
    def form(self):
        if self.request.method == 'POST':
            return CompanyEditForm(instance=self.edit_company, data=self.request.POST)
        else:
            return CompanyEditForm(instance=self.edit_company, initial={'name': self.default_name, 'website': self.default_website, 'domains': self.default_domain})

    @login_required
    def as_view(request, community_id):
        view = AddCompany(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            new_company = view.form.save()
            if 'for_member' in request.POST and request.POST.get('for_member'):
                for_member = request.POST.get('for_member')
                member = Member.objects.get(community=view.community, id=request.POST.get('for_member'))
                member.company = view.edit_company
                member.save()
                return redirect('member_profile', member_id=member.id)
            return redirect('company_profile', company_id=new_company.id)

        if 'for_member' in request.GET and request.GET.get('for_member'):
            try: 
                member = Member.objects.get(community=view.community, id=request.GET.get('for_member'))
                (identity, domain) = member.email_address.split('@', maxsplit=1)
                view.default_domain = domain
                view.default_website = 'https://'+domain
                view.default_name = domain.rsplit('.', maxsplit=1)[0].replace('-', ' ').title()
                view.for_member = request.GET.get('for_member')
            except Exception as e:
                pass
        return render(request, "savannahv2/company_add.html", view.context)

class EditCompany(SavannahView):
    def __init__(self, request, company_id):
        self.edit_company = get_object_or_404(Company, id=company_id)
        super().__init__(request, self.edit_company.community.id)
        self.active_tab = "company"

    @property
    def form(self):
        if self.request.method == 'POST':
            return CompanyEditForm(instance=self.edit_company, data=self.request.POST)
        else:
            return CompanyEditForm(instance=self.edit_company)

    @login_required
    def as_view(request, company_id):
        view = EditCompany(request, company_id)
        is_staff = view.edit_company.is_staff

        if request.method == "POST" and view.form.is_valid():
            edited_company = view.form.save()
            if edited_company.is_staff != is_staff:
                for member in Member.objects.filter(company=edited_company):
                    if edited_company.is_staff != is_staff and member.role != Member.BOT:
                        if edited_company.is_staff:
                            member.role = Member.STAFF
                        else:
                            member.role = Member.COMMUNITY
                        member.save()
            return redirect('company_profile', company_id=edited_company.id)

        return render(request, "savannahv2/company_edit.html", view.context)

from django.http import JsonResponse
@login_required
def tag_company(request, community_id):
    community = get_object_or_404(Community, id=community_id)
    if request.method == "POST":
        try:
            company_id = request.POST.get('company_id')
            company = Company.objects.get(community=community, id=company_id)
            tag_id = request.POST.get('tag_select')
            company.set_tag_by_name(tag_id)
            return JsonResponse({'success': True, 'errors':None})
        except Exception as e:
            return JsonResponse({'success':False, 'errors':str(e)})
    return JsonResponse({'success':False, 'errors':'Only POST method supported'})
    