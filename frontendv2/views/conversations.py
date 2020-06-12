import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe

from corm.models import *
from frontendv2.views import SavannahFilterView

class Conversations(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "conversations"
        
        self._membersChart = None
        self._channelsChart = None

        self.RESULTS_PER_PAGE = 25

        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'search' in request.GET:
            self.search = request.GET.get('search', "").lower()
        else:
            self.search = None
        self.result_count = 0


    @property
    def all_conversations(self):
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        if self.tag:
            conversations = conversations.filter(tags=self.tag)

        if self.role:
            conversations = conversations.filter(speaker__role=self.role)

        if self.search:
            conversations = conversations.filter(content__icontains=self.search)

        conversations = conversations.annotate(speaker_name=F('speaker__name'), tag_count=Count('tags'), source_name=F('channel__source__name'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        self.result_count = conversations.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return conversations[start:start+self.RESULTS_PER_PAGE]

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return min(10, pages+1)

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return [page+1 for page in range(min(10, pages+1))]

    def getConversationsChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))
            if self.tag:
                conversations = conversations.filter(tags=self.tag)

            if self.role:
                conversations = conversations.filter(speaker__role=self.role)

            if self.search:
                conversations = conversations.filter(content__icontains=self.search)
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
            from_colors = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc']
            next_color = 0
            channels = Channel.objects.filter(source__community=self.community)
            convo_filter = Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
            if self.role:
                convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
            if self.search:
                convo_filter = convo_filter & Q(conversation__content__icontains=self.search)

            channels = channels.annotate(conversation_count=Count('conversation', filter=convo_filter))

            channels = channels.annotate(source_connector=F('source__connector'), source_icon=F('source__icon_name'), color=F('tag__color'))
            for c in channels.order_by("-conversation_count"):
                if c.conversation_count == 0:
                    continue
                if not c.color:
                    c.color = from_colors[next_color]
                    next_color += 1
                    if next_color >= len(from_colors):
                        next_color = 0    

                counts[c] = c.conversation_count
            self._channelsChart = [("%s (%s)" % (channel.name, ConnectionManager.display_name(channel.source_connector)), count, channel.color) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 8:
                other_count = sum([count for channel, count, color in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:7]
                self._channelsChart.append(("Other", other_count, 'dfdfdf'))
        return self._channelsChart

    @property
    def channel_names(self):
        chart = self.getChannelsChart()
        return str([channel[0] for channel in chart])

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart]

    @property
    def channel_colors(self):
        chart = self.getChannelsChart()
        return ['#'+channel[2] for channel in chart]

    @property
    def most_active(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        convo_filter = Q(speaker_in__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        if self.tag:
            convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)
        if self.search:
            convo_filter = convo_filter & Q(speaker_in__content__icontains=self.search)

        members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter))
        for m in members:
            if m.conversation_count > 0:
                activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:20]

    @property
    def most_connected(self):
        if self.search:
            return []
        members = Member.objects.filter(community=self.community)
        connection_filter = Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        if self.tag:
            connection_filter = connection_filter & Q(connections__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)
        members = members.annotate(connection_count=Count('connections', filter=connection_filter))
        connection_counts = dict()
        for m in members:
            if m.connection_count > 0:
                connection_counts[m] = m.connection_count
        most_connected = [(member, count) for member, count in sorted(connection_counts.items(), key=operator.itemgetter(1))]
        most_connected.reverse()
        return most_connected[:20]

    @login_required
    def as_view(request, community_id):
        view = Conversations(request, community_id)
        return render(request, 'savannahv2/conversations.html', view.context)
