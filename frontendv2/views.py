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
    def __init__(self, community_id):
        self.community = get_object_or_404(Community, id=community_id)
    
    @property 
    def member_count(self):
        return self.community.member_set.all().count()
        
    @property 
    def conversation_count(self):
        return Conversation.objects.filter(channel__source__community=self.community).count()
        
    @property 
    def activity_count(self):
        return Activity.objects.filter(community=self.community).count()
        
    @property
    def open_tasks_count(self):
        return Task.objects.filter(community=self.community, done__isnull=True).count()

    @property
    def tasks_complete_percent(self):
        all_tasks = Task.objects.filter(community=self.community).count()
        return int(100 * (all_tasks - self.open_tasks_count) / all_tasks)

    @property
    def most_active(self):
        activity_counts = dict()
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

    @property
    def members_by_month(self):
        counts = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        for m in Member.objects.filter(community=self.community).order_by("date_added"):
            counts[m.date_added.month-1] += 1
        for i, count in enumerate(counts):
            if i > 0 and count > 0:
                counts[i] = counts[i] + counts[i-1]
        return counts

    @property
    def conversations_by_month(self):
        all_conversations = Conversation.objects.filter(channel__source__community=self.community)
        counts = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        for c in all_conversations:
            counts[c.timestamp.month-1] += 1
        return counts

    @property
    def channel_names(self):
        channels = [c.name for c in Channel.objects.filter(source__community=self.community)]
        channels.sort()
        return channels[:5]

    @property
    def channel_counts(self):
        channel_percents = list()
        for c in self.channel_names:
            channel_count = Conversation.objects.filter(channel__name=c).count()
            channel_percents.append(channel_count)
        return channel_percents[:5]

    @property
    def channel_percents(self):
        all_conversations = Conversation.objects.filter(channel__source__community=self.community).count()
        channel_percents = list()
        for c in self.channel_names:
            channel_count = Conversation.objects.filter(channel__name=c).count()
            channel_percents.append(int(100 * channel_count / all_conversations))
        return channel_percents

@login_required
def dashboard(request, community_id):
    communities = Community.objects.filter(owner=request.user)
    request.session['community'] = community_id
    dashboard = Dashboard(community_id)

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "dashboard": dashboard,
    }
    return render(request, 'savannahv2/dashboard.html', context)
