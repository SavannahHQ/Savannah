import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Min, Max, Avg, ExpressionWrapper, fields
from django.utils.safestring import mark_safe

from corm.models import *
from frontendv2.views import SavannahFilterView
from frontendv2.views.charts import PieChart
from frontendv2 import colors as savannah_colors

class Conversations(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "conversations"
        self.charts = set()

        self._membersChart = None
        self._channelsChart = None
        self._tagsChart = None
        self._rolesChart = None
        self._responseTimes = None

        self.RESULTS_PER_PAGE = 25

        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'conversation_search' in request.GET:
            self.conversation_search = request.GET.get('conversation_search', "").lower()
        else:
            self.conversation_search = None
        self.result_count = 0


    @property
    def all_conversations(self):
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        if self.tag:
            conversations = conversations.filter(tags=self.tag)

        if self.role:
            conversations = conversations.filter(speaker__role=self.role)

        if self.conversation_search:
            conversations = conversations.filter(content__icontains=self.conversation_search)

        conversations = conversations.select_related('channel', 'channel__source', 'speaker').prefetch_related('tags').order_by('-timestamp')
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

    def getResponseTimes(self):
        if not self._responseTimes:
            range_span = datetime.timedelta(days=self.timespan)
            range_1_end = datetime.datetime.utcnow()
            range_1_start = range_1_end - range_span

            replies = Conversation.objects.filter(speaker__community_id=self.community, thread_start__isnull=True, timestamp__gte=range_1_start, timestamp__lte=range_1_end)
            if self.tag:
                replies = replies.filter(Q(tags=self.tag) | Q(replies__tags=self.tag))

            if self.role:
                replies = replies.filter(replies__speaker__role=self.role)

            if self.conversation_search:
                replies = replies.filter(Q(content__icontains=self.conversation_search) | Q(replies__content__icontains=self.conversation_search))

            replies = replies.annotate(first_response=Min('replies__timestamp'))
            replies = replies.filter(first_response__isnull=False, first_response__gt=F('timestamp'))
            response_time = ExpressionWrapper(F('first_response') - F('timestamp'), output_field=fields.DurationField())
            replies = replies.annotate(response_time=response_time)
            self._responseTimes = replies.aggregate(avg=Avg('response_time'), min=Min('response_time'), max=Max('response_time'))
        return self._responseTimes

    @property
    def min_response_time(self):
        response_times = self.getResponseTimes()
        if response_times['min'] is None:
            return None
        return response_times['min'] - datetime.timedelta(microseconds=response_times['min'].microseconds)

    @property
    def max_response_time(self):
        response_times = self.getResponseTimes()
        if response_times['max'] is None:
            return None
        return response_times['max'] - datetime.timedelta(microseconds=response_times['max'].microseconds)

    @property
    def avg_response_time(self):
        response_times = self.getResponseTimes()
        if response_times['avg'] is None:
            return None
        return response_times['avg'] - datetime.timedelta(microseconds=response_times['avg'].microseconds)

    def getConversationsChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if self.tag:
                conversations = conversations.filter(tags=self.tag)

            if self.role:
                conversations = conversations.filter(speaker__role=self.role)

            if self.conversation_search:
                conversations = conversations.filter(content__icontains=self.conversation_search)
            conversations = conversations.order_by("timestamp")

            for m in conversations:
                month = self.trunc_date(m.timestamp)
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
        return self.timespan_chart_keys(months)

    @property
    def conversations_chart_counts(self):
        (months, counts) = self.getConversationsChart()
        return [counts.get(month, 0) for month in self.timespan_chart_keys(months)]

    def channelsChart(self):
        if not self._channelsChart:
            channels = list()
            counts = dict()
            channels = Channel.objects.filter(source__community=self.community)
            convo_filter = Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
            if self.role:
                convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
            if self.conversation_search:
                convo_filter = convo_filter & Q(conversation__content__icontains=self.conversation_search)

            channels = channels.annotate(conversation_count=Count('conversation', filter=convo_filter))

            channels = channels.annotate(source_connector=F('source__connector'), source_icon=F('source__icon_name'), color=F('tag__color'))
            for c in channels.order_by("-conversation_count"):
                if c.conversation_count == 0:
                    continue
                counts[c] = c.conversation_count
            self._channelsChart = PieChart("channelsChart", title="Conversations by Channel", limit=8)
            for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                self._channelsChart.add("%s (%s)" % (channel.name, ConnectionManager.display_name(channel.source_connector)), count, channel.color)
        self.charts.add(self._channelsChart)
        return self._channelsChart

    def tagsChart(self):
        if not self._tagsChart:
            counts = dict()
            tags = Tag.objects.filter(community=self.community)
            convo_filter = Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
            if self.role:
                convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
            if self.conversation_search:
                convo_filter = convo_filter & Q(conversation__content__icontains=self.conversation_search)

            tags = tags.annotate(conversation_count=Count('conversation', filter=convo_filter))

            for t in tags:
                counts[t] = t.conversation_count
            self._tagsChart = PieChart("tagsChart", title="Conversations by Tag", limit=12)
            for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                if count > 0:
                    self._tagsChart.add("#%s" % tag.name, count, tag.color)
        self.charts.add(self._tagsChart)
        return self._tagsChart

    def rolesChart(self):
        if not self._rolesChart:
            counts = dict()
            colors = {
                Member.COMMUNITY: savannah_colors.MEMBER.COMMUNITY,
                Member.STAFF: savannah_colors.MEMBER.STAFF,
                Member.BOT: savannah_colors.MEMBER.BOT
            }
            members = Member.objects.filter(community=self.community)
            convo_filter = Q(speaker_in__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if self.tag:
                convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
            if self.role:
                members = members.filter(role=self.role)
            if self.conversation_search:
                convo_filter = convo_filter & Q(speaker_in__content__icontains=self.conversation_search)
            #convo_filter = convo_filter & Q(speaker_in__speaker_id=F('id'))
            members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter)).filter(conversation_count__gt=0)

            for m in members:
                if m.role in counts:
                    counts[m.role] += m.conversation_count
                else:
                    counts[m.role] = m.conversation_count
            self._rolesChart = PieChart("rolesChart", title="Conversations by Role")
            for role, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                self._rolesChart.add(Member.ROLE_NAME[role], count, colors[role])
        self.charts.add(self._rolesChart)
        return self._rolesChart

    @property
    def most_active(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        convo_filter = Q(speaker_in__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)
        if self.conversation_search:
            convo_filter = convo_filter & Q(speaker_in__content__icontains=self.conversation_search)

        members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter)).filter(conversation_count__gt=0).prefetch_related('tags')
        for m in members:
            if m.conversation_count > 0:
                activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:20]

    @property
    def most_connected(self):
        if self.conversation_search:
            return []
        members = Member.objects.filter(community=self.community)
        connection_filter = Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            connection_filter = connection_filter & Q(connections__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)
        members = members.annotate(connection_count=Count('connections', filter=connection_filter)).filter(connection_count__gt=0).prefetch_related('tags')
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
