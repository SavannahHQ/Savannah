import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

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
            recent_conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30), tags=self.tag)
        else:
            recent_conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        for c in recent_conversations:
            for p in c.participants.all():
                if p in activity_counts:
                    activity_counts[p] = activity_counts[p] + 1
                else:
                    activity_counts[p] = 1
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def most_connected(self):
        if self.tag:
            connections = MemberConnection.objects.filter(from_member__community=self.community, last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30), to_member__tags=self.tag)
        else:
            connections = MemberConnection.objects.filter(from_member__community=self.community, last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        connection_counts = dict()
        for c in connections:
                if c.from_member in connection_counts:
                    connection_counts[c.from_member] = connection_counts[c.from_member] + 1
                else:
                    connection_counts[c.from_member] = 1
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
                channel = c.channel.name
                if channel not in channels:
                    channels.append(channel)
                if channel not in counts:
                    counts[channel] = 1
                else:
                    counts[channel] += 1
            self._channelsChart = [(channel, count) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
        return self._channelsChart

    @property
    def channel_names(self):
        chart = self.getChannelsChart()
        return [channel[0] for channel in chart[:5]]

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart[:5]]


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
            recent_conversations = Conversation.objects.filter(channel__source__community=self.community, tags=self.tag).order_by("-timestamp")
        else:
            recent_conversations = Conversation.objects.filter(channel__source__community=self.community).order_by("-timestamp")
        members = dict()
        for c in recent_conversations:
            for m in c.participants.all():
                if m not in members:
                    members[m] = c.timestamp
        recently_active = [(member, tstamp) for member, tstamp in sorted(members.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def most_active(self):
        activity_counts = dict()
        if self.tag:
            recent_conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30), tags=self.tag)
        else:
            recent_conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        for c in recent_conversations:
            for p in c.participants.all():
                if p in activity_counts:
                    activity_counts[p] = activity_counts[p] + 1
                else:
                    activity_counts[p] = 1
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def most_connected(self):
        if self.tag:
            connections = MemberConnection.objects.filter(from_member__community=self.community, last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30), to_member__tags=self.tag)
        else:
            connections = MemberConnection.objects.filter(from_member__community=self.community, last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        connection_counts = dict()
        for c in connections:
                if c.from_member in connection_counts:
                    connection_counts[c.from_member] = connection_counts[c.from_member] + 1
                else:
                    connection_counts[c.from_member] = 1
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
            if self.tag:
                members = Member.objects.filter(community=self.community, tags=self.tag).order_by("name")
            else:
                members = Member.objects.filter(community=self.community).order_by("name")
            for m in members:
                for tag in m.tags.all():
                    if tag not in tags:
                        tags.append(tag)
                    if tag not in counts:
                        counts[tag] = 1
                    else:
                        counts[tag] += 1
            self._tagsChart = [('#'+tag.name, count, '#'+tag.color) for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
        return self._tagsChart

    @property
    def tag_names(self):
        chart = self.getTagsChart()
        return [tag[0] for tag in chart[:5]]

    @property
    def tag_counts(self):
        chart = self.getTagsChart()
        return [tag[1] for tag in chart[:5]]

    @property
    def tag_colors(self):
        chart = self.getTagsChart()
        return [tag[2] for tag in chart[:5]]


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
        "view": members,
    }
    return render(request, 'savannahv2/members.html', context)
