import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.contrib import messages

from corm.models import *
from corm.connectors import ConnectionManager
from frontendv2.views import SavannahView

class MemberMergeSuggestions(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "members"
    
    @property
    def all_suggestions(self):
        suggestions = SuggestMemberMerge.objects.filter(community=self.community, status__isnull=True).select_related('source_member').select_related('destination_member').order_by("-created_at")
        return suggestions

    @login_required
    def as_view(request, community_id):
        view = MemberMergeSuggestions(request, community_id)

        if request.method == 'POST':
            if 'reject' in request.POST:
                suggestion_id = request.POST.get('reject')
                suggestion = SuggestMemberMerge.objects.get(id=suggestion_id)
                suggestion.reject(request.user)
                messages.info(request, "Suggested rejected, you won't see it again")
            elif 'accept' in request.POST:
                success_count = 0
                selected = request.POST.getlist('selected')
                for suggestion_id in selected:
                    try:
                        suggestion = SuggestMemberMerge.objects.get(id=suggestion_id)
                        suggestion.accept(request.user)
                        success_count += 1
                    except:
                        pass
                if len(selected) > 0:
                    messages.success(request, "<b>%s</b> %s been merged" % (success_count, pluralize(len(selected), "Member has", "Members have")))
                else:
                    messages.warning(request, "You haven't selected any merge suggestions")

            return redirect('member_merge_suggestions', community_id=community_id)
        return render(request, 'savannahv2/member_merge_suggestions.html', view.context)

class ContributionSuggestions(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "contributions"
    
    @property
    def all_suggestions(self):
        suggestions = SuggestConversationAsContribution.objects.filter(community=self.community, status__isnull=True).order_by("-conversation__timestamp")
        suggestions = suggestions.select_related('conversation', 'source')
        return suggestions

    @login_required
    def as_view(request, community_id):
        view = ContributionSuggestions(request, community_id)

        if request.method == 'POST':
            if 'reject' in request.POST:
                suggestion_id = request.POST.get('reject')
                suggestion = SuggestConversationAsContribution.objects.get(id=suggestion_id)
                suggestion.reject(request.user)
                messages.info(request, "Suggested rejected, you won't see it again")
            elif 'accept' in request.POST:
                success_count = 0
                selected = request.POST.getlist('selected')
                for suggestion_id in selected:
                    try:
                        suggestion = SuggestConversationAsContribution.objects.get(id=suggestion_id)
                        suggestion.accept(request.user)
                        success_count += 1
                    except:
                        pass
                if len(selected) > 0:
                    messages.success(request, "<b>%s</b> %s been added" % (success_count, pluralize(len(selected), "Contribution has", "Contributions have")))
                else:
                    messages.warning(request, "You haven't selected any contribution suggestions")

            return redirect('conversation_as_contribution_suggestions', community_id=community_id)
        return render(request, 'savannahv2/conversation_as_contribution_suggestions.html', view.context)

class CompanyCreationSuggestions(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "companies"
    
    @property
    def all_suggestions(self):
        suggestions = SuggestCompanyCreation.objects.filter(community=self.community, status__isnull=True).order_by("-created_at")
        return suggestions

    @login_required
    def as_view(request, community_id):
        view = CompanyCreationSuggestions(request, community_id)

        if request.method == 'POST':
            if 'reject' in request.POST:
                suggestion_id = request.POST.get('reject')
                suggestion = SuggestCompanyCreation.objects.get(id=suggestion_id)
                suggestion.reject(request.user)
                messages.info(request, "Suggested rejected, you won't see it again")
            elif 'accept' in request.POST:
                success_count = 0
                selected = request.POST.getlist('selected')
                for suggestion_id in selected:
                    try:
                        suggestion = SuggestCompanyCreation.objects.get(id=suggestion_id)
                        suggestion.accept(request.user)
                        success_count += 1
                    except:
                        pass
                if len(selected) > 0:
                    messages.success(request, "<b>%s</b> %s been created" % (success_count, pluralize(len(selected), "Company has", "Companies have")))
                else:
                    messages.warning(request, "You haven't selected any company suggestions")

            return redirect('company_suggestions', community_id=community_id)
        return render(request, 'savannahv2/company_suggestions.html', view.context)

class TagSuggestions(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "tags"
    
    @property
    def all_suggestions(self):
        suggestions = SuggestTag.objects.filter(community=self.community, status__isnull=True).order_by("-score")
        return suggestions

    @login_required
    def as_view(request, community_id):
        view = TagSuggestions(request, community_id)

        if request.method == 'POST':
            if 'reject' in request.POST:
                suggestion_id = request.POST.get('reject')
                suggestion = SuggestTag.objects.get(id=suggestion_id)
                suggestion.reject(request.user)
                messages.info(request, "Suggestion rejected, you won't see it again")
            elif 'accept' in request.POST:
                success_count = 0
                selected = request.POST.getlist('selected')
                for suggestion_id in selected:
                    try:
                        suggestion = SuggestTag.objects.get(id=suggestion_id)
                        suggestion.accept(request.user)
                        success_count += 1
                    except:
                        pass
                if len(selected) > 0:
                    messages.success(request, "<b>%s</b> %s been added" % (success_count, pluralize(len(selected), "Tag has", "Tags have")))
                else:
                    messages.warning(request, "You haven't selected any tag suggestions")

            return redirect('tag_suggestions', community_id=community_id)
        return render(request, 'savannahv2/tag_suggestions.html', view.context)


class TaskSuggestions(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "projects"
    
    @property
    def all_suggestions(self):
        suggestions = SuggestTask.objects.filter(community=self.community, status__isnull=True).order_by("-created_at")
        return suggestions

    @login_required
    def as_view(request, community_id):
        view = TaskSuggestions(request, community_id)

        if request.method == 'POST':
            if 'reject' in request.POST:
                suggestion_id = request.POST.get('reject')
                suggestion = SuggestTask.objects.get(id=suggestion_id)
                suggestion.reject(request.user)
                messages.info(request, "Suggestion rejected, you won't see it again")
            elif 'accept' in request.POST:
                success_count = 0
                selected = request.POST.getlist('selected')
                for suggestion_id in selected:
                    try:
                        suggestion = SuggestTask.objects.get(id=suggestion_id)
                        suggestion.accept(request.user)
                        success_count += 1
                    except Exception as e:
                        print(e)
                        pass
                if len(selected) > 0:
                    messages.success(request, "<b>%s</b> %s been added" % (success_count, pluralize(len(selected), "Task has", "Task have")))
                else:
                    messages.warning(request, "You haven't selected any task suggestions")

            return redirect('task_suggestions', community_id=community_id)
        return render(request, 'savannahv2/task_suggestions.html', view.context)

