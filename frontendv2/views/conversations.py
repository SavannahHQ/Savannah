import operator
import datetime
from django.shortcuts import render, get_object_or_404, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Min, Max, Avg, ExpressionWrapper, fields
from django.db.models.functions import Trunc
from django.utils.safestring import mark_safe

from corm.models import *
from frontendv2.views import SavannahFilterView
from frontendv2.views.charts import PieChart, LineChart 
from frontendv2 import colors as savannah_colors
from frontendv2.models import PublicDashboard

class Conversations(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "conversations"
        self.charts = set()
        self.filter.update({
            'timespan': True,
            'custom_timespan': True,
            'member_role': True,
            'member_tag': True,
            'member_company': True,
            'tag': True,
            'source': True,
            'contrib_type': False,
        })

        self._membersChart = None
        self._channelsChart = None
        self._tagsChart = None
        self._rolesChart = None
        self._responseTimes = None
        self._responseRate = None
        self._allConversations = None

        self.RESULTS_PER_PAGE = 25

        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'clear' in request.GET and request.GET.get('clear') == 'all':
            request.session['conversation_search'] = None
            request.session['filter_link'] = None

        self.conversation_search = None
        try:
            if 'conversation_search' in request.GET:
                if request.GET.get('conversation_search') == '':
                    request.session['conversation_search'] = None
                else:
                    self.conversation_search = request.GET.get('conversation_search', "").lower()
                    request.session['conversation_search'] = self.conversation_search
            elif 'conversation_search' in request.session:
                self.conversation_search = request.session.get('conversation_search')
        except:
            self.conversation_search = None
            request.session['conversation_search'] = None

        self.filter_link = None
        try:
            if 'link' in request.GET:
                if request.GET.get('link') == '':
                    request.session['filter_link'] = None
                else:
                    self.filter_link = Hyperlink.objects.get(community=self.community, id=int(request.GET.get('link')))
                    request.session['filter_link'] = request.GET.get('link')
            elif 'filter_link' in request.session:
                self.filter_link = Hyperlink.objects.get(community=self.community, id=int(request.session.get('filter_link')))
        except:
            self.filter_link = None
            request.session['filter_link'] = None

        self.result_count = 0

        self.chart_type = request.session.get('conversations_chart_type', 'basic')
        if 'by_convo' in request.GET:
            self.chart_type = 'basic'
        elif 'by_tag' in request.GET:
            self.chart_type = 'tag'
        elif 'by_source' in request.GET:
            self.chart_type = 'source'
        elif 'by_role' in request.GET:
            self.chart_type = 'role'
        request.session['conversations_chart_type'] = self.chart_type

    def _displayed_conversations(self):
        if self._allConversations is None:
            conversations = Conversation.objects.filter(channel__source__community=self.community)
            conversations = conversations.filter(timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    conversations = conversations.exclude(channel__source=self.source)
                else:
                    conversations = conversations.filter(channel__source=self.source)

            if self.tag:
                conversations = conversations.filter(tags=self.tag)

            if self.member_company:
                conversations = conversations.filter(speaker__company=self.member_company)

            if self.member_tag:
                conversations = conversations.filter(speaker__tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    conversations = conversations.exclude(speaker__role=self.role)
                else:
                    conversations = conversations.filter(speaker__role=self.role)

            if self.conversation_search:
                conversations = conversations.filter(content__icontains=self.conversation_search)

            if self.filter_link:
                conversations = conversations.filter(links=self.filter_link)
            self.result_count = conversations.count()
            self._allConversations = conversations
        return self._allConversations

    @property
    def all_conversations(self):
        conversations = self._displayed_conversations().select_related('channel', 'channel__source', 'speaker').prefetch_related('tags').order_by('-timestamp')
        
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return conversations[start:start+self.RESULTS_PER_PAGE]

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

    @property
    def median_response_time(self):
        if self._responseTimes:
            return self._responseTimes
        else:
            replies = Conversation.objects.filter(speaker__community_id=self.community, thread_start__isnull=True, timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    replies = replies.exclude(channel__source=self.source)
                else:
                    replies = replies.filter(channel__source=self.source)
            if self.tag:
                replies = replies.filter(Q(tags=self.tag) | Q(replies__tags=self.tag))

            if self.member_company:
                replies = replies.filter(replies__speaker__company=self.member_company)

            if self.member_tag:
                replies = replies.filter(replies__speaker__tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    replies = replies.exclude(replies__speaker__role=self.role)
                else:
                    replies = replies.filter(replies__speaker__role=self.role)

            if self.conversation_search:
                replies = replies.filter(Q(content__icontains=self.conversation_search) | Q(replies__content__icontains=self.conversation_search))

            if self.filter_link:
                replies = replies.filter(links=self.filter_link)

            replies = replies.annotate(first_response=Min('replies__timestamp'))
            replies = replies.filter(first_response__isnull=False, first_response__gt=F('timestamp'))
            response_time = ExpressionWrapper(F('first_response') - F('timestamp'), output_field=fields.DurationField())
            replies = replies.annotate(response_time=response_time)
            values = replies.values_list('response_time', flat=True).order_by('response_time')
            count = len(values)
            if count < 1:
                return None
            if count % 2 == 1:
                median = values[int(round(count/2))]
            else:
                med1, med2 = values[int(count/2-1):int(count/2+1)]
                median = (med1 + med2)/(2.0)
            self._responseTimes = median - datetime.timedelta(microseconds=median.microseconds)
            return self._responseTimes

    @property
    def response_rate(self):
        if self._responseRate:
            return self._responseRate
        else:
            convos = Conversation.objects.filter(speaker__community_id=self.community, timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    convos = convos.exclude(channel__source=self.source)
                else:
                    convos = convos.filter(channel__source=self.source)
            if self.tag:
                convos = convos.filter(Q(tags=self.tag) | Q(replies__tags=self.tag))

            if self.member_company:
                convos = convos.filter(speaker__company=self.member_company)

            if self.member_tag:
                convos = convos.filter(speaker__tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    convos = convos.exclude(speaker__role=self.role)
                else:
                    convos = convos.filter(speaker__role=self.role)

            if self.conversation_search:
                convos = convos.filter(Q(content__icontains=self.conversation_search) | Q(replies__content__icontains=self.conversation_search))

            if self.filter_link:
                convos = convos.filter(links=self.filter_link)

            total = self.conversation_count
            if total == 0:
                return 0
            responded = convos.annotate(reponse_count=Count('replies', unique=True)).filter(reponse_count__gt=0).count()
            # print("total: %s\nreponded: %s" % (total, responded))
            self._responseRate = 100 * responded / total
            return self._responseRate

    @property 
    def speaker_count(self):
        members = self.community.member_set.all()
        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)

        conversation_filter = Q(speaker_in__timestamp__gte=self.rangestart, speaker_in__timestamp__lte=self.rangeend)
        if self.source:
            if self.exclude_source:
                conversation_filter = conversation_filter & ~Q(speaker_in__channel__source=self.source)
            else:
                conversation_filter = conversation_filter & Q(speaker_in__channel__source=self.source)
        if self.tag:
            conversation_filter = conversation_filter & Q(speaker_in__tags=self.tag)
        if self.filter_link:
            conversation_filter = conversation_filter & Q(speaker_in__links=self.filter_link)
        members = members.annotate(activity_count=Count('speaker_in', filter=conversation_filter)).filter(activity_count__gt=0)
        return members.count()

    @property
    def conversation_count(self):
        convos = self._displayed_conversations()
        return convos.count()

    def conversationsChart(self):
        if self.chart_type == 'tag':
            return self.getConversationsChartByTag()
        elif self.chart_type == 'source':
            return self.getConversationsChartBySource()
        elif self.chart_type == 'role':
            return self.getConversationsChartByRole()
        else:
            return self.getBasicConversationsChart()

    def getBasicConversationsChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    conversations = conversations.exclude(channel__source=self.source)
                else:
                    conversations = conversations.filter(channel__source=self.source)

            if self.tag:
                conversations = conversations.filter(tags=self.tag)

            if self.member_company:
                conversations = conversations.filter(speaker__company=self.member_company)

            if self.member_tag:
                conversations = conversations.filter(speaker__tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    conversations = conversations.exclude(speaker__role=self.role)
                else:
                    conversations = conversations.filter(speaker__role=self.role)

            if self.conversation_search:
                conversations = conversations.filter(content__icontains=self.conversation_search)
            if self.filter_link:
                conversations = conversations.filter(links=self.filter_link)
            conversations = conversations.order_by("timestamp")
            seen = conversations.annotate(month=Trunc('timestamp', self.trunc_span)).values('month').annotate(convo_count=Count('id', distinct=True)).order_by('month')
            for c in seen:
                month = self.trunc_date(c['month'])

                if month not in months:
                    months.append(month)
                counts[month] = c['convo_count']

            self._membersChart = LineChart('conversation_graph', 'Conversations')
            self._membersChart.set_keys(self.timespan_chart_keys(sorted(months)))
            self._membersChart.add('Conversations', counts, savannah_colors.CONVERSATION)
        self.charts.add(self._membersChart)
        return self._membersChart
    
    def getConversationsChartByTag(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Q(conversation__channel__source__community=self.community, conversation__timestamp__gte=self.rangestart, conversation__timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    conversations = conversations & ~Q(conversation__channel__source=self.source)
                else:
                    conversations = conversations & Q(conversation__channel__source=self.source)

            if self.tag:
                conversations = conversations & Q(conversation__tags=self.tag)

            if self.member_company:
                conversations = conversations & Q(conversation__speaker__company=self.member_company)

            if self.member_tag:
                conversations = conversations & Q(conversation__speaker__tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    conversations = conversations & ~Q(conversation__speaker__role=self.role)
                else:
                    conversations = conversations & Q(conversation__speaker__role=self.role)

            if self.conversation_search:
                conversations = conversations & Q(conversation__content__icontains=self.conversation_search)
            if self.filter_link:
                conversations = conversations & Q(conversation__links=self.filter_link)

            seen = Tag.objects.filter(community=self.community).annotate(month=Trunc('conversation__timestamp', self.trunc_span, filter=conversations)).values('month', 'name', 'color').annotate(convo_count=Count('conversation__id', distinct=True, filter=conversations)).order_by('month')

            for tag in seen:
                if tag.get('month') is None:
                    continue;
                month = self.trunc_date(tag['month'])
                if month is None or month == 'None':
                    continue;

                if tag['name'] not in counts:
                    counts[tag['name']] = (dict(), tag['color'])
                if month not in counts[tag['name']][0]:
                    counts[tag['name']][0][month] = tag['convo_count']
                else:
                    counts[tag['name']][0][month] += tag['convo_count']

            self._membersChart = LineChart('conversation_graph', 'Conversations by Tags', limit=8)
            self._membersChart.stacked = True
            self._membersChart.set_keys(self.timespan_chart_keys(sorted(months)))
            for tag, data in counts.items():
                self._membersChart.add(tag, data[0], data[1] or savannah_colors.OTHER)
        self.charts.add(self._membersChart)
        return self._membersChart

    def getConversationsChartBySource(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Q(channel__conversation__timestamp__gte=self.rangestart, channel__conversation__timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    conversations = conversations & ~Q(channel__source=self.source)
                else:
                    conversations = conversations & Q(channel__source=self.source)

            if self.tag:
                conversations = conversations & Q(channel__conversation__tags=self.tag)

            if self.member_company:
                conversations = conversations & Q(channel__conversation__speaker__company=self.member_company)

            if self.member_tag:
                conversations = conversations & Q(channel__conversation__speaker__tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    conversations = conversations & ~Q(channel__conversation__speaker__role=self.role)
                else:
                    conversations = conversations & Q(channel__conversation__speaker__role=self.role)

            if self.conversation_search:
                conversations = conversations & Q(channel__conversation__content__icontains=self.conversation_search)
            if self.filter_link:
                conversations = conversations & Q(channel__conversation__links=self.filter_link)

            seen = Source.objects.filter(community=self.community)
            seen = seen.annotate(month=Trunc('channel__conversation__timestamp', self.trunc_span, filter=conversations)).values('month', 'name', 'connector').annotate(convo_count=Count('channel__conversation__id', distinct=True, filter=conversations)).order_by('-convo_count')
            for tag in seen:
                if tag.get('month') is None:
                    continue;
                month = self.trunc_date(tag['month'])
                if month is None or month == 'None':
                    continue;

                if tag['name'] not in counts:
                    counts[tag['name']] = (dict(), tag['connector'])
                if month not in counts[tag['name']][0]:
                    counts[tag['name']][0][month] = tag['convo_count']
                else:
                    counts[tag['name']][0][month] += tag['convo_count']

            self._membersChart = LineChart('conversation_graph', 'Conversations by Source', limit=8)
            self._membersChart.stacked = True
            self._membersChart.set_keys(self.timespan_chart_keys(sorted(months)))
            for tag, data in counts.items():
                self._membersChart.add("%s (%s)" % (ConnectionManager.display_name(data[1]), tag), data[0], None)
        self.charts.add(self._membersChart)
        return self._membersChart

    def getConversationsChartByRole(self):
        if not self._membersChart:
            months = list()
            counts = dict()

            conversations = Q(speaker_in__timestamp__gte=self.rangestart, speaker_in__timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    conversations = conversations & ~Q(speaker_in__channel__source=self.source)
                else:
                    conversations = conversations & Q(speaker_in__channel__source=self.source)

            if self.tag:
                conversations = conversations & Q(speaker_in__tags=self.tag)

            if self.member_company:
                conversations = conversations & Q(company=self.member_company)

            if self.member_tag:
                conversations = conversations & Q(tags=self.member_tag)

            if self.role:
                if self.role == Member.BOT:
                    conversations = conversations & ~Q(role=self.role)
                else:
                    conversations = conversations & Q(role=self.role)

            if self.conversation_search:
                conversations = conversations & Q(speaker_in__content__icontains=self.conversation_search)
            if self.filter_link:
                conversations = conversations & Q(speaker_in__links=self.filter_link)

            seen = Member.objects.filter(community=self.community)
            seen = seen.annotate(month=Trunc('speaker_in__timestamp', self.trunc_span, filter=conversations)).values('month', 'role').annotate(convo_count=Count('speaker_in', distinct=True, filter=conversations)).order_by('month')

            for tag in seen:
                if tag.get('month') is None:
                    continue;
                month = self.trunc_date(tag['month'])
                if month is None or month == 'None':
                    continue;

                if tag['role'] not in counts:
                    counts[tag['role']] = (dict(), None)
                if month not in counts[tag['role']][0]:
                    counts[tag['role']][0][month] = tag['convo_count']
                else:
                    counts[tag['role']][0][month] += tag['convo_count']

            self._membersChart = LineChart('conversation_graph', 'Conversations by Role', limit=8)
            self._membersChart.stacked = True
            self._membersChart.set_keys(self.timespan_chart_keys(sorted(months)))
            for tag, data in counts.items():
                color = savannah_colors.MEMBER
                if tag == 'staff':
                    color = savannah_colors.MEMBER.STAFF
                elif tag == 'bot':
                    color = savannah_colors.MEMBER.BOT
                self._membersChart.add(tag.title(), data[0], color)
        self.charts.add(self._membersChart)
        return self._membersChart

    def channelsChart(self):
        if not self._channelsChart:
            channels = list()
            counts = dict()
            channels = Channel.objects.filter(source__community=self.community)
            convo_filter = Q(conversation__timestamp__gte=self.rangestart, conversation__timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    channels = channels.exclude(source=self.source)
                else:
                    channels = channels.filter(source=self.source)
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
            if self.member_company:
                convo_filter = convo_filter & Q(conversation__speaker__company=self.member_company)
            if self.member_tag:
                convo_filter = convo_filter & Q(conversation__speaker__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    convo_filter = convo_filter & ~Q(conversation__speaker__role=self.role)
                else:
                    convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
            if self.conversation_search:
                convo_filter = convo_filter & Q(conversation__content__icontains=self.conversation_search)
            if self.filter_link:
                convo_filter = convo_filter & Q(conversation__links=self.filter_link)

            channels = channels.annotate(conversation_count=Count('conversation', filter=convo_filter))

            channels = channels.annotate(source_connector=F('source__connector'), source_icon=F('source__icon_name'), color=F('tag__color'))
            for c in channels:
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
            convo_filter = Q(conversation__timestamp__gte=self.rangestart, conversation__timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    convo_filter = convo_filter & ~Q(conversation__channel__source=self.source)
                else:
                    convo_filter = convo_filter & Q(conversation__channel__source=self.source)
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
                tags = tags.exclude(id=self.tag.id)
            if self.member_company:
                convo_filter = convo_filter & Q(conversation__speaker__company=self.member_company)
            if self.member_tag:
                convo_filter = convo_filter & Q(conversation__speaker__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    convo_filter = convo_filter & ~Q(conversation__speaker__role=self.role)
                else:
                    convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
            if self.conversation_search:
                convo_filter = convo_filter & Q(conversation__content__icontains=self.conversation_search)
            if self.filter_link:
                convo_filter = convo_filter & Q(conversation__links=self.filter_link)

            tags = tags.annotate(conversation_count=Count('conversation', filter=convo_filter))

            for t in tags:
                counts[t] = t.conversation_count
            self._tagsChart = PieChart("tagsChart", title="Conversations by Tag", limit=12)
            for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                if count > 0:
                    self._tagsChart.add(tag.name, count, tag.color)
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
            convo_filter = Q(speaker_in__timestamp__gte=self.rangestart, speaker_in__timestamp__lte=self.rangeend)
            if self.source:
                if self.exclude_source:
                    convo_filter = convo_filter & ~Q(speaker_in__channel__source=self.source)
                else:
                    convo_filter = convo_filter & Q(speaker_in__channel__source=self.source)
            if self.tag:
                convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
            if self.member_company:
                members = members.filter(company=self.member_company)
            if self.member_tag:
                members = members.filter(tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    members = members.exclude(role=self.role)
                else:
                    members = members.filter(role=self.role)
            if self.conversation_search:
                convo_filter = convo_filter & Q(speaker_in__content__icontains=self.conversation_search)
            if self.filter_link:
                convo_filter = convo_filter & Q(speaker_in__links=self.filter_link)
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
        convo_filter = Q(speaker_in__timestamp__gte=self.rangestart, speaker_in__timestamp__lte=self.rangeend)
        if self.source:
            if self.exclude_source:
                convo_filter = convo_filter & ~Q(speaker_in__channel__source=self.source)
            else:
                convo_filter = convo_filter & Q(speaker_in__channel__source=self.source)
        if self.tag:
            convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)
        if self.conversation_search:
            convo_filter = convo_filter & Q(speaker_in__content__icontains=self.conversation_search)
        if self.filter_link:
            convo_filter = convo_filter & Q(speaker_in__links=self.filter_link)

        members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter)).filter(conversation_count__gt=0).prefetch_related('tags').order_by('-conversation_count')
        return members[:20]

    @property
    def most_connected(self):
        if self.conversation_search or self.filter_link:
            return []
        members = Member.objects.filter(community=self.community)
        connection_filter = Q(memberconnection__last_connected__gte=self.rangestart, memberconnection__last_connected__lte=self.rangeend)
        if self.source:
            if self.exclude_source:
                members = members.exclude(connections__contact__source=self.source)
            else:
                members = members.filter(connections__contact__source=self.source)
        if self.tag:
            connection_filter = connection_filter & Q(connections__tags=self.tag)
        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)
        members = members.annotate(connection_count=Count('connections', filter=connection_filter)).filter(connection_count__gt=0).prefetch_related('tags').order_by('-connection_count')
        return members[:20]

    @property
    def top_links(self):
        links = Hyperlink.objects.filter(community=self.community, ignored=False)
        convo_filter = Q(conversation__timestamp__gte=self.rangestart, conversation__timestamp__lte=self.rangeend)
        if self.source:
            if self.exclude_source:
                convo_filter = convo_filter & ~Q(conversation__channel__source=self.source)
            else:
                convo_filter = convo_filter & Q(conversation__channel__source=self.source)
        if self.tag:
            convo_filter = convo_filter & Q(conversation__tags=self.tag)
        if self.member_company:
            convo_filter = convo_filter & Q(conversation__speaker__company=self.member_company)
        if self.member_tag:
            convo_filter = convo_filter & Q(conversation__speaker__tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                convo_filter = convo_filter & ~Q(conversation__speaker__role=self.role)
            else:
                convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
        if self.conversation_search:
            convo_filter = convo_filter & Q(conversation__content__icontains=self.conversation_search)
        if self.filter_link:
            convo_filter = convo_filter & Q(conversation__links=self.filter_link)

        links = links.annotate(conversation_count=Count('conversation', filter=convo_filter)).filter(conversation_count__gt=0).order_by('-conversation_count')
        return links[:10]

    @property
    def top_link_sites(self):
        links = Hyperlink.objects.filter(community=self.community, ignored=False)
        convo_filter = Q(conversation__timestamp__gte=self.rangestart, conversation__timestamp__lte=self.rangeend)
        if self.source:
            if self.exclude_source:
                convo_filter = convo_filter & ~Q(conversation__channel__source=self.source)
            else:
                convo_filter = convo_filter & Q(conversation__channel__source=self.source)
        if self.tag:
            convo_filter = convo_filter & Q(conversation__tags=self.tag)
        if self.member_company:
            convo_filter = convo_filter & Q(conversation__speaker__company=self.member_company)
        if self.member_tag:
            convo_filter = convo_filter & Q(conversation__speaker__tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                convo_filter = convo_filter & ~Q(conversation__speaker__role=self.role)
            else:
                convo_filter = convo_filter & Q(conversation__speaker__role=self.role)
        if self.conversation_search:
            convo_filter = convo_filter & Q(conversation__content__icontains=self.conversation_search)
        if self.filter_link:
            convo_filter = convo_filter & Q(conversation__links=self.filter_link)

        links = links.values('host').annotate(conversation_count=Count('conversation', filter=convo_filter)).filter(conversation_count__gt=0).order_by('-conversation_count')
        return links[:10]


    @login_required
    def as_view(request, community_id):
        view = Conversations(request, community_id)
        return render(request, 'savannahv2/conversations.html', view.context)

    @login_required
    def publish(request, community_id):
        if 'cancel' in request.GET:
            return redirect('conversations', community_id=community_id)
            
        conversations = Conversations(request, community_id)
        return conversations.publish_view(request, PublicDashboard.CONVERSATIONS, 'public_conversations')

    def public(request, dashboard_id):
        dashboard = get_object_or_404(PublicDashboard, id=dashboard_id)
        conversations = Conversations(request, dashboard.community.id)
        context = dashboard.apply(conversations)
        conversations.chart_type = 'basic'
        if 'conversations_chart_type' in dashboard.filters and dashboard.filters['conversations_chart_type'] is not None:
            conversations.chart_type = dashboard.filters['conversations_chart_type']
        if 'conversation_search' in dashboard.filters and dashboard.filters['conversation_search'] is not None:
            conversations.conversation_search = dashboard.filters['conversation_search']
        if 'filter_link' in dashboard.filters and dashboard.filters['filter_link'] is not None:
            conversations.filter_link = Hyperlink.objects.get(id=dashboard.filters['filter_link'])
        if not request.user.is_authenticated:
            dashboard.count()
        return render(request, 'savannahv2/public/conversations.html', context)

    def filters_as_dict(self, request):
        filters = super().filters_as_dict(request)
        filters['conversations_chart_type'] = self.chart_type
        filters['conversation_search'] = request.session.get('conversation_search', None)
        filters['filter_link'] = request.session.get('filter_link', None)
        return filters
        
@login_required
def ignore_hyperlink(request, community_id, hyperlink_id):
    try:
        link = Hyperlink.objects.get(id=hyperlink_id)
        community = get_object_or_404(Community, Q(owner=request.user) | Q(managers__in=request.user.groups.all()), id=community_id)
    except:
        messages.error(request, "Could not find hyperlink to ignore")

    link.ignored = True
    link.save()
    undo_link = reverse('show_hyperlink', kwargs={'community_id':community.id, 'hyperlink_id':link.id})
    messages.success(request, "You will no longer see <a href=\"%s\" target=\"_blank\">%s</a> in your results.&nbsp;&nbsp;<a href=\"%s\">Undo</a>" % (link.url, link.url, undo_link))

    return redirect('conversations', community_id=community.id)

@login_required
def show_hyperlink(request, community_id, hyperlink_id):
    try:
        link = Hyperlink.objects.get(id=hyperlink_id)
        community = get_object_or_404(Community, Q(owner=request.user) | Q(managers__in=request.user.groups.all()), id=community_id)
    except:
        messages.error(request, "Could not find hyperlink to ignore")

    link.ignored = False
    link.save()
    undo_link = reverse('show_hyperlink', kwargs={'community_id':community.id, 'hyperlink_id':link.id})
    messages.success(request, "Link has been restored to your results")

    return redirect('conversations', community_id=community.id)
    