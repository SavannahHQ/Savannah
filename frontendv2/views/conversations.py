import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max

from corm.models import *

class Conversations:
    def __init__(self, community_id, tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._channelsChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None

    @property
    def all_conversations(self):
        if self.tag:
            conversations = Conversation.objects.filter(channel__source__community=self.community, tags=self.tag).annotate(participant_count=Count('participants'), tag_count=Count('tags'), channel_name=F('channel__name')).order_by('-timestamp')
        else:
            conversations = Conversation.objects.filter(channel__source__community=self.community).annotate(participant_count=Count('participants'), tag_count=Count('tags'), channel_name=F('channel__name')).order_by('-timestamp')
        return conversations[:100]

    def getConversationsChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            if self.tag:
                members = Conversation.objects.filter(channel__source__community=self.community, tags=self.tag).order_by("timestamp")
            else:
                members = Conversation.objects.filter(channel__source__community=self.community).order_by("timestamp")
            for m in members:
                month = m.timestamp.month
                if month not in months:
                    months.append(month)
                if month not in counts:
                    counts[month] = 1
                else:
                    counts[month] += 1
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def conversations_chart_months(self):
        (months, counts) = self.getConversationsChart()
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return [names[month-1] for month in months[-12:]]

    @property
    def conversations_chart_counts(self):
        (months, counts) = self.getConversationsChart()
        return [counts[month] for month in months[-12:]]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            total = 0
            if self.tag:
                channels = Channel.objects.filter(source__community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__tags=self.tag)))
            else:
                channels = Channel.objects.filter(source__community=self.community).annotate(conversation_count=Count('conversation'))
            for c in channels:
                counts[c.name] = c.conversation_count
            self._channelsChart = [(channel, count) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 8:
                other_count = sum([count for channel, count in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:7]
                self._channelsChart.append(("Other", other_count))
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
def conversations(request, community_id):
    communities = Community.objects.filter(owner=request.user)
    request.session['community'] = community_id
    if 'tag' in request.GET:
        conversations = Conversations(community_id, tag=request.GET.get('tag'))
    else:
        conversations = Conversations(community_id)

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": conversations.community,
        "active_tab": "conversations",
        "view": conversations,
    }
    return render(request, 'savannahv2/conversations.html', context)
