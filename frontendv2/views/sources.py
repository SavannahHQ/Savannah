import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.contrib import messages
from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView

class Sources(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "sources"

    def all_sources(self):
        return Source.objects.filter(community=self.community).annotate(channel_count=Count('channel', distinct=True), member_count=Count('contact', distinct=True))

    @login_required
    def as_view(request, community_id):
        view = Sources(request, community_id)
        return render(request, "savannahv2/sources.html", view.context)

class Channels(SavannahView):
    def __init__(self, request, community_id, source_id):
        self.source = get_object_or_404(Source, id=source_id)
        super().__init__(request, community_id)
        self.active_tab = "sources"

    def all_channels(self):
        return Channel.objects.filter(source=self.source).annotate(conversation_count=Count('conversation', distinct=True))

    def available_channels(self):
        tracked_channel_ids = [channel.origin_id for channel in Channel.objects.filter(source=self.source)]
        channels = []
        if self.source.connector in ConnectionManager.CONNECTOR_PLUGINS:
            plugin  = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
            source_channels = plugin.get_channels(self.source)
            for channel in source_channels:
                if channel['id'] not in tracked_channel_ids:
                    channels.append(channel)
        return sorted(channels, key=lambda c: c['count'], reverse=True)

    def track_channel(self, origin_id):
        if self.source.connector in ConnectionManager.CONNECTOR_PLUGINS:
            plugin  = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
            source_channels = plugin.get_channels(self.source)
            for channel in source_channels:
                if channel['id'] == origin_id:
                    c, created = Channel.objects.get_or_create(origin_id=origin_id, source=self.source, name=channel['name'])
                    if created:
                        messages.success(self.request, "%s has been added to your community tracker, and will appear in the next import")

    @login_required
    def as_view(request, community_id, source_id):
        view = Channels(request, community_id, source_id)

        if request.method == 'POST':
            channel_origin_id = request.POST.get('track_channel_id')
            view.track_channel(channel_origin_id)
            return redirect('channels', community_id=community_id, source_id=source_id)

        return render(request, "savannahv2/channels.html", view.context)