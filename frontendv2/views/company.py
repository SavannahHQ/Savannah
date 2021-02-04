import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.db.models.functions import Trunc

from django.contrib import messages
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView
from frontendv2.views.charts import PieChart, ChartColors

class CompanyProfile(SavannahView):
    def __init__(self, request, company_id):
        self.company = get_object_or_404(Company, id=company_id)
        super().__init__(request, self.company.community.id)
        self.active_tab = "company"
        self._sourcesChart = None
        self._engagementChart = None
        self.timespan=90

    @property
    def all_members(self):
        return Member.objects.filter(community=self.community, company=self.company).prefetch_related('tags').order_by('name')

    @property
    def sources_chart(self):
        if not self._sourcesChart:
            counts = dict()
            other_count = 0
            identity_filter = Q(contact__member__company=self.company)
            sources = Source.objects.filter(community=self.community).annotate(identity_count=Count('contact', filter=identity_filter))
            for source in sources:
                if source.identity_count == 0:
                    continue
                counts[source] = source.identity_count

            self._sourcesChart = PieChart("sourcesChart", title="Member Sources", limit=8)
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

    @login_required
    def as_view(request, company_id):
        view = CompanyProfile(request, company_id)

        return render(request, "savannahv2/company.html", view.context)

class Companies(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "company"
        self._membersChart = None
        self._conversationsChart = None
        self._contributionsChart = None
        self._company_colors = dict()

    def suggestion_count(self):
        return SuggestCompanyCreation.objects.filter(community=self.community, status__isnull=True).count()

    def all_companies(self):
        return Company.objects.filter(community=self.community).annotate(member_count=Count('member', distinct=True)).order_by('name')

    def members_chart(self):
        if not self._membersChart:
            companies = Company.objects.filter(community=self.community, is_staff=False).annotate(member_count=Count('member')).filter(member_count__gt=0).order_by('-member_count')

            chart_colors = ChartColors()
            self._membersChart = PieChart("membersChart", title="Members by Company")
            self._membersChart.set_show_legend(False)
            for company in companies:
                if company.tag:
                    self._company_colors[company.id] = company.tag.color
                else:
                    self._company_colors[company.id] = chart_colors.next()
                self._membersChart.add(company.name, company.member_count, data_color=self._company_colors[company.id])
        self.charts.add(self._membersChart)
        return self._membersChart

    def conversations_chart(self):
        if not self._conversationsChart:
            companies = Company.objects.filter(community=self.community, is_staff=False).annotate(convo_count=Count('member__speaker_in')).filter(convo_count__gt=0).order_by('-convo_count')

            self._conversationsChart = PieChart("conversationsChart", title="Conversations by Company")
            self._conversationsChart.set_show_legend(False)
            for company in companies:
                self._conversationsChart.add(company.name, company.convo_count, data_color=self._company_colors[company.id])
        self.charts.add(self._conversationsChart)
        return self._conversationsChart

    def contributions_chart(self):
        if not self._contributionsChart:
            companies = Company.objects.filter(community=self.community, is_staff=False).annotate(contrib_count=Count('member__contribution')).filter(contrib_count__gt=0).order_by('-contrib_count')

            self._contributionsChart = PieChart("contributionsChart", title="Contributions by Company")
            self._contributionsChart.set_show_legend(False)
            for company in companies:
                self._contributionsChart.add(company.name, company.contrib_count, data_color=self._company_colors[company.id])
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
            view.form.save()
            if 'for_member' in request.POST and request.POST.get('for_member'):
                for_member = request.POST.get('for_member')
                member = Member.objects.get(community=view.community, id=request.POST.get('for_member'))
                member.company = view.edit_company
                member.save()
                return redirect('member_profile', member_id=member.id)
            return redirect('companies', community_id=community_id)

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
            return redirect('companies', community_id=view.community.id)

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
            if tag_id == '':
                for member in Member.objects.filter(company=company):
                    member.tags.remove(company.tag)
                company.tag = None
            else:
                tag = Tag.objects.get(community=community, id=tag_id)
                for member in Member.objects.filter(company=company):
                    member.tags.add(tag)
                company.tag = tag
            company.save()
            return JsonResponse({'success': True, 'errors':None})
        except Exception as e:
            return JsonResponse({'success':False, 'errors':str(e)})
    return JsonResponse({'success':False, 'errors':'Only POST method supported'})
    