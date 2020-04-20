import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max

from corm.models import *

class Dashboard:
    def __init__(self, community_id, tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._channelsChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None
    
    @property 
    def member_count(self):
        if self.tag:
            return self.community.member_set.filter(tags=self.tag).count()
        else:
            return self.community.member_set.all().count()
        
    @property 
    def conversation_count(self):
        if self.tag:
            return Conversation.objects.filter(channel__source__community=self.community, tags=self.tag).count()
        else:
            return Conversation.objects.filter(channel__source__community=self.community).count()
        
    @property 
    def activity_count(self):
        if self.tag:
            return Activity.objects.filter(community=self.community, tags=self.tag).count()
        else:
            return Activity.objects.filter(community=self.community).count()
        
    @property
    def open_tasks_count(self):
        if self.tag:
            return Task.objects.filter(community=self.community, done__isnull=True, tags=self.tag).count()
        else:
            return Task.objects.filter(community=self.community, done__isnull=True).count()

    @property
    def tasks_complete_percent(self):
        if self.tag:
            all_tasks = Task.objects.filter(community=self.community, tags=self.tag).count()
        else:
            all_tasks = Task.objects.filter(community=self.community).count()
        if all_tasks == 0:
            return 0
        return int(100 * (all_tasks - self.open_tasks_count) / all_tasks)

    @property
    def most_active(self):
        activity_counts = dict()
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30), conversation__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
        for m in members:
            activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def most_connected(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30), connections__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))))

        connection_counts = dict()
        for m in members:
            connection_counts[m] = m.connection_count
        most_connected = [(member, count) for member, count in sorted(connection_counts.items(), key=operator.itemgetter(1))]
        most_connected.reverse()
        return most_connected[:10]

    def getMembersChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()
            total = 0
            if self.tag:
                members = Member.objects.filter(community=self.community, date_added__gte=datetime.datetime.now() - datetime.timedelta(days=180), tags=self.tag).order_by("date_added")
                total = Member.objects.filter(community=self.community, date_added__lt=datetime.datetime.now() - datetime.timedelta(days=180), tags=self.tag).count()
            else:
                members = Member.objects.filter(community=self.community, date_added__gte=datetime.datetime.now() - datetime.timedelta(days=180)).order_by("date_added")
                total = Member.objects.filter(community=self.community, date_added__lt=datetime.datetime.now() - datetime.timedelta(days=180)).count()
            for m in members:
                total += 1
                month = str(m.date_added)[:7]
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        return [month for month in months[-12:]]

    @property
    def members_chart_counts(self):
        (months, counts) = self.getMembersChart()
        return [counts[month] for month in months[-12:]]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            counts = dict()
            total = 0
            if self.tag:
                conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), tags=self.tag).annotate(source_name=F('channel__source__name')).order_by("timestamp")
            else:
                conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180)).annotate(source_name=F('channel__source__name')).order_by("timestamp")
            for c in conversations:
                if c.source_name not in counts:
                    counts[c.source_name] = 1
                else:
                    counts[c.source_name] += 1
            self._channelsChart = [(channel, count) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 8:
                other_count = sum([count for tag, count in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:7]
                self._channelsChart.append(("Other", other_count, "#efefef"))
        return self._channelsChart

    @property
    def channel_names(self):
        chart = self.getChannelsChart()
        return [channel[0] for channel in chart]

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart]


@login_required
def dashboard(request, community_id):
    communities = Community.objects.filter(owner=request.user)
    request.session['community'] = community_id
    if 'tag' in request.GET:
        dashboard = Dashboard(community_id, tag=request.GET.get('tag'))
    else:
        dashboard = Dashboard(community_id)

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": dashboard.community,
        "active_tab": "dashboard",
        "dashboard": dashboard,
    }
    return render(request, 'savannahv2/dashboard.html', context)
