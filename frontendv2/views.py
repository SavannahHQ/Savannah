import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max

from corm.models import *

# Create your views here.
def index(request):
    sayings = [
        "Herd your cats",
        "Build a better community",
        "Manage your community relationships"
    ]
    return render(request, 'savannah/index.html', {'sayings': sayings})

@login_required
def home(request):
    communities = Community.objects.filter(owner=request.user)
    context = {
        "communities": communities,
    }
    return render(request, 'savannah/home.html', context)

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
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation'))
        for m in members:
            activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def most_connected(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(connections__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections'))

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
                members = Member.objects.filter(community=self.community, tags=self.tag).order_by("date_added")
            else:
                members = Member.objects.filter(community=self.community).order_by("date_added")
            for m in members:
                total += 1
                month = m.date_added.month
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return [names[month-1] for month in months[-12:]]

    @property
    def members_chart_counts(self):
        (months, counts) = self.getMembersChart()
        return [counts[month] for month in months[-12:]]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            total = 0
            if self.tag:
                conversations = Conversation.objects.filter(channel__source__community=self.community, tags=self.tag).order_by("timestamp")
            else:
                conversations = Conversation.objects.filter(channel__source__community=self.community).order_by("timestamp")
            for c in conversations:
                total += 1
                if not c.channel_id in channel_names:
                    channel_names[c.channel_id] = c.channel.name
                channel = channel_names[c.channel_id]
                if channel not in channels:
                    channels.append(channel)
                if channel not in counts:
                    counts[channel] = 1
                else:
                    counts[channel] += 1
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


class Members:
    def __init__(self, community_id, tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._tagsChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None
    
    @property
    def all_members(self):
        if self.tag:
            members = Member.objects.filter(community=self.community, tags=self.tag)
        else:
            members = Member.objects.filter(community=self.community)
        return members

    @property
    def new_members(self):
        if self.tag:
            members = Member.objects.filter(community=self.community, tags=self.tag)
        else:
            members = Member.objects.filter(community=self.community)
        return members.order_by("-date_added")[:10]

    @property
    def recently_active(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(last_active=Max('conversation__timestamp', filter=Q(conversation__timestamp__isnull=False, conversation__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(last_active=Max('conversation__timestamp', filter=Q(conversation__timestamp__isnull=False)))
        actives = dict()
        for m in members:
            if m.last_active is not None:
                actives[m] = m.last_active
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def most_active(self):
        activity_counts = dict()
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation'))
        for m in members:
            activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def most_connected(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(connections__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections'))

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
                members = Member.objects.filter(community=self.community, tags=self.tag).order_by("date_added")
            else:
                members = Member.objects.filter(community=self.community).order_by("date_added")
            for m in members:
                total += 1
                month = m.date_added.month
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return [names[month-1] for month in months[-12:]]

    @property
    def members_chart_counts(self):
        (months, counts) = self.getMembersChart()
        return [counts[month] for month in months[-12:]]

    def getTagsChart(self):
        if not self._tagsChart:
            tags = list()
            counts = dict()
            total = 0
            tags = Tag.objects.filter(community=self.community).annotate(member_count=Count('member')).order_by('-member_count')
            for t in tags:
                counts[t] = t.member_count
            self._tagsChart = [('#'+tag.name, count, '#'+tag.color) for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._tagsChart) > 8:
                other_count = sum([count for tag, count, color in self._tagsChart[7:]])
                self._tagsChart = self._tagsChart[:7]
                self._tagsChart.append(("Other", other_count, "#efefef"))
        return self._tagsChart

    @property
    def tag_names(self):
        chart = self.getTagsChart()
        return [tag[0] for tag in chart]

    @property
    def tag_counts(self):
        chart = self.getTagsChart()
        return [tag[1] for tag in chart]

    @property
    def tag_colors(self):
        chart = self.getTagsChart()
        return [tag[2] for tag in chart]


@login_required
def members(request, community_id):
    communities = Community.objects.filter(owner=request.user)
    request.session['community'] = community_id
    if 'tag' in request.GET:
        members = Members(community_id, tag=request.GET.get('tag'))
    else:
        members = Members(community_id)

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": members.community,
        "active_tab": "members",
        "view": members,
    }
    return render(request, 'savannahv2/members.html', context)
