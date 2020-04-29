import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe

from corm.models import *

class Conversations:
    def __init__(self, community_id, tag=None, member_tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._channelsChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None
        if member_tag:
            self.member_tag = get_object_or_404(Tag, name=member_tag)
        else:
            self.member_tag = None

    @property
    def all_conversations(self):
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        if self.tag:
            conversations = conversations.filter(tags=self.tag)

        if self.member_tag:
            conversations = conversations.filter(participants__tags=self.member_tag)

        conversations = conversations.annotate(participant_count=Count('participants'), tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        return conversations[:100]

    def getConversationsChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))
            if self.tag:
                conversations = conversations.filter(tags=self.tag)

            if self.member_tag:
                conversations = conversations.filter(participants__tags=self.member_tag)
            conversations = conversations.order_by("timestamp")

            for m in conversations:
                month = str(m.timestamp)[:10]
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
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(180)]
        date_list.reverse()
        return [str(day)[:10] for day in date_list]

    @property
    def conversations_chart_counts(self):
        (months, counts) = self.getConversationsChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(180)]
        date_list.reverse()
        return [counts.get(str(day)[:10], 0) for day in date_list]
        #return [counts[month] for month in months]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            total = 0
            channels = Channel.objects.filter(source__community=self.community)
            if self.tag:
                if self.member_tag:
                    channels = channels.annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), conversation__tags=self.tag, conversation__participants__tags=self.member_tag)))
                else:
                    channels = channels.annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), conversation__tags=self.tag)))
            else:
                if self.member_tag:
                    channels = channels.annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), conversation__participants__tags=self.member_tag)))
                else:
                    channels = channels.annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))))

            channels = channels.annotate(source_icon=F('source__icon_name'))
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
        return mark_safe(str([channel[0] for channel in chart]))

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart]


@login_required
def conversations(request, community_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))
    request.session['community'] = community_id
    kwargs = dict()
    if 'tag' in request.GET:
        kwargs['tag'] = request.GET.get('tag')

    if 'member_tag' in request.GET:
        kwargs['member_tag'] = request.GET.get('member_tag')

    conversations = Conversations(community_id, **kwargs)
    try:
        user_member = Member.objects.get(user=request.user, community=conversations.community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": conversations.community,
        "active_tab": "conversations",
        "view": conversations,
    }
    return render(request, 'savannahv2/conversations.html', context)
