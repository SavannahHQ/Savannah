import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.contrib import messages
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView

class Companies(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "company"

    def all_companies(self):
        return Company.objects.filter(community=self.community).annotate(member_count=Count('member', distinct=True))

    @login_required
    def as_view(request, community_id):
        view = Companies(request, community_id)
        if request.method == 'POST':
            if 'delete_company' in request.POST:
                company = get_object_or_404(Company, id=request.POST.get('delete_company'))
                context = view.context
                context.update({
                    'object_type':"Company", 
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
        fields = ['name', 'website', 'is_staff']

class AddCompany(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.edit_company = Company(community=self.community)
        self.active_tab = "company"

    @property
    def form(self):
        if self.request.method == 'POST':
            return CompanyEditForm(instance=self.edit_company, data=self.request.POST)
        else:
            return CompanyEditForm(instance=self.edit_company)

    @login_required
    def as_view(request, community_id):
        view = AddCompany(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('companies', community_id=community_id)

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
                    if edited_company.is_staff != is_staff and member.role != MemberConnection.BOT:
                        if edited_company.is_staff:
                            member.role = Member.STAFF
                        else:
                            member.role = Member.COMMUNITY
                        member.save()
            return redirect('companies', community_id=view.community.id)

        return render(request, "savannahv2/community_edit.html", view.context)

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
    