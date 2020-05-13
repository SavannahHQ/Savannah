import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe

from corm.models import *
from frontendv2.views import SavannahView

class Conversations(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "conversations"
        
        self._membersChart = None
        self._channelsChart = None

        if 'member_tag' in request.GET:
            self.member_tag = get_object_or_404(Tag, name=request.GET.get('member_tag'))
        else:
            self.member_tag = None

    @property
    def all_conversations(self):
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        if self.tag:
            conversations = conversations.filter(tags=self.tag)

        if self.member_tag:
            conversations = conversations.filter(participants__tags=self.member_tag)

        conversations = conversations.annotate(speaker_name=F('speaker__name'), tag_count=Count('tags'), source_name=F('channel__source__name'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
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
                month = str(m.timestamp)[:7]
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
        return months

    @property
    def conversations_chart_counts(self):
        (months, counts) = self.getConversationsChart()
        return [counts[month] for month in months]

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

            channels = channels.annotate(source_name=F('source__name'), source_icon=F('source__icon_name'))
            for c in channels:
                counts["%s (%s)" % (c.name, c.source_name)] = c.conversation_count
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
    def as_view(request, community_id):
        view = Conversations(request, community_id)
        return render(request, 'savannahv2/conversations.html', view.context)
