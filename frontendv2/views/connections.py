import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe
from django.http import JsonResponse

from corm.models import *
from frontendv2.views import SavannahFilterView
from frontendv2.views.charts import PieChart

class Connections(SavannahFilterView):
    def __init__(self, request, community_id, json=False):
        self._is_json = json
        super().__init__(request, community_id)
        self.active_tab = "connections"
        self._connectionsChart = None
        self._sourcesChart = None

    def _add_sources_message(self):
        if self._is_json:
            pass
        else:
            super()._add_sources_message()

    def getConnectionsChart(self):
        if not self._connectionsChart:
            months = list()
            counts = dict()

            connections = MemberConnection.objects.filter(community=self.community)
            if self.member_company:
                connections = connections.filter(Q(from_member__company=self.member_company)|Q(to_member__company=self.member_company))
            if self.member_tag:
                connections = connections.filter(Q(from_member__tags=self.member_tag)|Q(to_member__tags=self.member_tag))
            if self.role:
                connections = connections.filter(Q(from_member__role=self.role)&Q(from_member__role=self.role))


            counts['prev'] = connections.filter(first_connected__lt=self.rangestart).count()

            connections = connections.filter(first_connected__gte=self.rangestart, first_connected__lte=self.rangeend)
            for c in connections:
                month = self.trunc_date(c.first_connected)
                if month not in months:
                    months.append(month)
                if month not in counts:
                    counts[month] = 1
                else:
                    counts[month] += 1
            self._connectionsChart = (months, counts)
        return self._connectionsChart
        
    @property
    def connections_chart_months(self):
        (months, counts) = self.getConnectionsChart()
        return self.timespan_chart_keys(months)

    @property
    def connections_chart_counts(self):
        (months, counts) = self.getConnectionsChart()
        cumulative_counts = []
        previous = counts['prev']
        for month in self.timespan_chart_keys(months):
            cumulative_counts.append(counts.get(month, 0)+previous)
            previous = cumulative_counts[-1]
        return cumulative_counts

    def sources_chart(self):
        channel_names = dict()
        if not self._sourcesChart:
            counts = dict()
            participants = Participant.objects.filter(community=self.community, timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
            if self.member_company:
                participants = participants.filter(Q(initiator__company=self.member_company)|Q(member__company=self.member_company))
            if self.member_tag:
                participants = participants.filter(Q(initiator__tags=self.member_tag)|Q(initiator__tags=self.member_tag))
            if self.role:
                participants = participants.filter(Q(initiator__role=self.role)&Q(initiator__role=self.role))

            participants = participants.annotate(source_connector=F('conversation__channel__source__connector')).values('source_connector')
            participants = participants.annotate(connection_count=Count('conversation', distinct=True)).order_by('-connection_count')

            self._sourcesChart = PieChart("sourcesChart", title="Connections by Source", limit=8)
            for c in participants.values('source_connector', 'connection_count'):
                self._sourcesChart.add(ConnectionManager.display_name(c['source_connector']), c['connection_count'])

        self.charts.add(self._sourcesChart)
        return self._sourcesChart

    @login_required
    def as_view(request, community_id):
        view = Connections(request, community_id)
        return render(request, 'savannahv2/connections.html', view.context)

    @login_required
    def as_json(request, community_id):
        view = Connections(request, community_id, json=True)
        nodes = list()
        links = list()
        member_map = dict()
        connection_counts = dict()
        connected = set()
        if view.timespan <= 31:
            timespan = view.timespan
        else:
            timespan = 30
        
        connections = MemberConnection.objects.filter(from_member__community=view.community, last_connected__gte=view.rangeend - datetime.timedelta(days=timespan), last_connected__lte=view.rangeend)
        if view.member_company:
            connections = connections.filter(Q(to_member__company=view.member_company)|Q(from_member__company=view.member_company))
        if view.member_tag:
            connections = connections.filter(Q(to_member__tags=view.member_tag)|Q(from_member__tags=view.member_tag))
        if view.role:
            connections = connections.filter(Q(to_member__role=view.role)&Q(from_member__role=view.role))
        connections = connections.select_related('from_member').prefetch_related('from_member__tags').order_by('-last_connected')

        for connection in connections:
            if connection.from_member_id != connection.to_member_id:
                if connection.to_member_id > connection.from_member_id:
                    connection_id = str(connection.to_member_id) + ":" + str(connection.from_member_id)
                else:
                    connection_id = str(connection.from_member_id) + ":" + str(connection.to_member_id)

                links.append({"source":connection.from_member_id, "target":connection.to_member_id})
                member_map[connection.from_member_id] = connection.from_member

                if not connection_id in connected:
                    connected.add(connection_id)

                    if connection.from_member_id not in connection_counts:
                        connection_counts[connection.from_member_id] = 1
                    else:
                        connection_counts[connection.from_member_id] += 1

                    if len(connected) >= 100000:
                        break


        for member_id, member in member_map.items():
            tag_color = None
            tags = member.tags.all()
            if len(tags) > 0:
                tag_color = tags[0].color
            if tag_color is None and member.role == Member.BOT:
                tag_color = "aeaeae"
            elif tag_color is None and member.role == Member.STAFF:
                tag_color = "36b9cc"
            if tag_color is None:
                tag_color = "1f77b4"
            
            nodes.append({"id":member_id, "name":member.name, "color":tag_color, "connections":connection_counts.get(member_id, 0)})
        

        return JsonResponse({"nodes":nodes, "links":links})
