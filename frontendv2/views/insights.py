import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, Min
from django.db.models.functions import Trunc, Lower
from django.http import JsonResponse
from django.contrib import messages
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import PieChart, ChartColors
from frontendv2 import colors

class InsightsList(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "profile"

        self.RESULTS_PER_PAGE = 25
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        self.result_count = 0
        self.show = request.GET.get('show', 'all')

    def _get_filtered_insights(self):
        insights = Insight.objects.filter(community=self.community, recipient=self.request.user).order_by('-timestamp')

        if self.show == "read":
            insights = insights.filter(unread=False)
        elif self.show == "unread":
            insights = insights.filter(unread=True)
        elif self.show == "positive":
            insights = insights.filter(level=Insight.InsightLevel.SUCCESS)
        elif self.show == "informative":
            insights = insights.filter(level=Insight.InsightLevel.INFO)
        elif self.show == "warnings":
            insights = insights.filter(level=Insight.InsightLevel.WARNING)
        elif self.show == "emergencies":
            insights = insights.filter(level=Insight.InsightLevel.DANGER)
        else:
            try:
                insight_id = int(self.show)
                insights = insights.filter(id=insight_id)
            except Exception as e:
                pass
        return insights

    @property
    def all_insights(self):
        insights = self._get_filtered_insights()
        self.result_count = insights.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return insights[start:start+self.RESULTS_PER_PAGE]

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

    @login_required
    def as_view(request, community_id):
        view = InsightsList(request, community_id)
        if request.method == 'POST':
            view.show = request.POST.get('show')
            insights = view._get_filtered_insights().filter(unread=True)
            count = insights.count()
            ret = insights.update(unread=False)
            print(ret)
            messages.success(request, "Marked %s insights as read." % count)
            return redirect(reverse('insights', kwargs={'community_id':community_id})+"?show="+view.show)

        return render(request, "savannahv2/insights.html", view.context)

def toggle_insight_read_state(request, community_id):
    community = get_object_or_404(Community, id=community_id)
    if request.method == "POST":
        try:
            insight_id = request.POST.get('insight_id')
            insight = get_object_or_404(Insight, id=insight_id, community=community, recipient=request.user)
            insight.unread = not insight.unread
            insight.save()
            return JsonResponse({'success': True, 'errors':None, 'id':insight.id, 'unread': insight.unread})
        except Exception as e:
            return JsonResponse({'success': False, 'errors':str(e)})

    return JsonResponse({'success': False, 'errors':'Only POST method supported'}, status=405)
