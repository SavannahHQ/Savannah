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
        suggestions = SuggestMemberMerge.objects.filter(community=self.community, status__isnull=True)
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
                selected = request.POST.getlist('selected')
                for suggestion_id in selected:
                    suggestion = SuggestMemberMerge.objects.get(id=suggestion_id)
                    suggestion.accept(request.user)
                if len(selected) > 0:
                    messages.success(request, "<b>%s</b> %s been merged" % (len(selected), pluralize(len(selected), "Member has", "Members have")))
                else:
                    messages.warning(request, "You haven't selected any merge suggestions")

            return redirect('member_merge_suggestions', community_id=community_id)
        return render(request, 'savannahv2/member_merge_suggestions.html', view.context)
