import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe
from django.http import JsonResponse

from corm.models import *
from frontendv2.views import SavannahView

class Connections(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "connections"
        self._connectionsChart = None
        self._sourcesChart = None

    def getConnectionsChart(self):
        if not self._connectionsChart:
            months = list()
            counts = dict()
            total = 0
            if self.tag:
                connections = MemberConnection.objects.filter(via__community=self.community).filter(Q(from_member__tags=self.tag)|Q(to_member__tags=self.tag)).order_by("first_connected")
            else:
                connections = MemberConnection.objects.filter(via__community=self.community).order_by("first_connected")
            for c in connections:
                total += 1
                month = str(c.first_connected)[:7]
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._connectionsChart = (months, counts)
        return self._connectionsChart
        
    @property
    def connections_chart_months(self):
        (months, counts) = self.getConnectionsChart()
        return months[-6:]

    @property
    def connections_chart_counts(self):
        (months, counts) = self.getConnectionsChart()
        return [counts[month] for month in months[-6:]]

    def getSourcesChart(self):
        channel_names = dict()
        if not self._sourcesChart:
            counts = dict()
            connections = MemberConnection.objects.filter(via__community=self.community, first_connected__gt=datetime.datetime.utcnow() - datetime.timedelta(days=180))
            if self.tag:
                connections = connections.filter(Q(from_member__tags=self.tag)|Q(to_member__tags=self.tag))

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
        return [channel[1] for channel in chart]

    @login_required
    def as_view(request, community_id):
        view = Connections(request, community_id)
        return render(request, 'savannahv2/connections.html', view.context)

    @login_required
    def as_json(request, community_id):
        view = Connections(request, community_id)
        nodes = list()
        links = list()
        member_map = dict()
        connection_counts = dict()
        connected = set()

        connections = MemberConnection.objects.filter(from_member__community=view.community, first_connected__gt=datetime.datetime.utcnow() - datetime.timedelta(days=180), last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        if view.tag:
            connections = connections.filter(Q(to_member__tags=view.tag)|Q(from_member__tags=view.tag))
        connections = connections.annotate(from_member_name=F('from_member__name'), to_member_name=F('to_member__name'))

        for connection in connections:
            if connection.from_member_id != connection.to_member_id:
                if not (connection.to_member_id, connection.from_member_id) in connected: 
                    links.append({"source":connection.from_member_id, "target":connection.to_member_id})
                    connected.add((connection.from_member_id, connection.to_member_id))
                    member_map[connection.from_member_id] = connection.from_member_name
                    member_map[connection.to_member_id] = connection.to_member_name
                    if connection.from_member_id not in connection_counts:
                        connection_counts[connection.from_member_id] = 1
                    else:
                        connection_counts[connection.from_member_id] += 1

                    if connection.to_member_id not in connection_counts:
                        connection_counts[connection.to_member_id] = 1
                    else:
                        connection_counts[connection.to_member_id] += 1

        for member_id, member_name in member_map.items():
            tag_color = "1f77b4"
            if connection_counts.get(member_id, 0) >= 3:
                tags = Tag.objects.filter(member__id=member_id)
                if len(tags) > 0:
                    tag_color = tags[0].color

            nodes.append({"id":member_id, "name":member_name, "color":tag_color, "connections":connection_counts.get(member_id, 0)})
                    
        return JsonResponse({"nodes":nodes, "links":links})
