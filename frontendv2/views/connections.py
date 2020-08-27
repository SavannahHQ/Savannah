import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe
from django.http import JsonResponse

from corm.models import *
from frontendv2.views import SavannahFilterView

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
            total = 0
            connections = MemberConnection.objects.filter(via__community=self.community)
            
            if self.tag:
                connections = connections.filter(Q(from_member__tags=self.tag)|Q(to_member__tags=self.tag))
            if self.role:
                connections = connections.filter(Q(from_member__role=self.role)&Q(to_member__role=self.role))

            connections = connections.order_by("first_connected")
            for c in connections:
                total += 1
                month = self.trunc_date(c.first_connected)
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._connectionsChart = (months, counts)
        return self._connectionsChart
        
    @property
    def connections_chart_months(self):
        (months, counts) = self.getConnectionsChart()
        return months[-self.timespan_chart_span:]

    @property
    def connections_chart_counts(self):
        (months, counts) = self.getConnectionsChart()
        return [counts[month]/2 for month in months[-self.timespan_chart_span:]]

    def getSourcesChart(self):
        channel_names = dict()
        if not self._sourcesChart:
            counts = dict()
            connections = MemberConnection.objects.filter(via__community=self.community, first_connected__gt=datetime.datetime.utcnow() - datetime.timedelta(days=self.timespan))
            if self.tag:
                connections = connections.filter(Q(from_member__tags=self.tag)|Q(to_member__tags=self.tag))
            if self.role:
                connections = connections.filter(Q(from_member__role=self.role)&Q(to_member__role=self.role))

            connections = connections.annotate(source_name=F('via__name'), source_connector=F('via__connector'), source_icon=F('via__icon_name'))
            for c in connections:
                source_name = "%s (%s)" % (c.source_name, ConnectionManager.display_name(c.source_connector))
                if source_name not in counts:
                    counts[source_name] = 1
                else:
                    counts[source_name] += 1
            self._sourcesChart = [(channel, count) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._sourcesChart) > 8:
                other_count = sum([count for channel, count in self._sourcesChart[7:]])
                self._sourcesChart = self._sourcesChart[:7]
                self._sourcesChart.append(("Other", other_count))
        return self._sourcesChart

    @property
    def source_names(self):
        chart = self.getSourcesChart()
        return mark_safe(str([channel[0] for channel in chart]))

    @property
    def source_counts(self):
        chart = self.getSourcesChart()
        return [channel[1]/2 for channel in chart]

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
        if view.timespan <= 30:
            timespan = view.timespan
        else:
            timespan = 30
        
        connections = MemberConnection.objects.filter(from_member__community=view.community, last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=timespan))
        if view.tag:
            connections = connections.filter(Q(to_member__tags=view.tag)|Q(from_member__tags=view.tag))
        if view.role:
            connections = connections.filter(Q(to_member__role=view.role)&Q(from_member__role=view.role))
        connections = connections.select_related('from_member').prefetch_related('from_member__tags').order_by('-last_connected')

        for connection in connections[:10000]:
            if connection.from_member_id != connection.to_member_id:
                if not connection.from_member_id in connected: 
                    links.append({"source":connection.from_member_id, "target":connection.to_member_id})
                    connected.add((connection.from_member_id, connection.to_member_id))
                    member_map[connection.from_member_id] = connection.from_member
                    if connection.from_member_id not in connection_counts:
                        connection_counts[connection.from_member_id] = 1
                    else:
                        connection_counts[connection.from_member_id] += 1


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
