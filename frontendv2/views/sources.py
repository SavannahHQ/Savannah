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
        if request.method == "POST":
            if 'remove_source' in request.POST:
                source = get_object_or_404(Source, id=request.POST.get('remove_source'))
                context = view.context
                context.update({'object_type':"Source", 'object_name': source.name, 'object_id': source.id})
                contacts_count = source.contact_set.all().count()
                channel_count = source.channel_set.all().count()
                conversation_count = Conversation.objects.filter(channel__source=source).count()
                context['object_dependencies'] = [
                    (contacts_count, pluralize(contacts_count, "identity", "identities")),
                    (channel_count, pluralize(channel_count, "channel")),
                    (conversation_count, pluralize(conversation_count, "conversation")),
                ]
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                source = get_object_or_404(Source, id=request.POST.get('object_id'))
                source_name = source.name
                source.delete()
                messages.success(request, "Delete source: <b>%s</b>" % source_name)
                return redirect('sources', community_id=community_id)
        return render(request, "savannahv2/sources.html", view.context)

class Channels(SavannahView):
    def __init__(self, request, community_id, source_id):
        super().__init__(request, community_id)
        self.source = get_object_or_404(Source, id=source_id, community=self.community)
        self.active_tab = "sources"
        self.available_channels = []

    def all_channels(self):
        return Channel.objects.filter(source=self.source).annotate(conversation_count=Count('conversation', distinct=True))

    def fetch_available_channels(self):
        tracked_channel_ids = [channel.origin_id for channel in Channel.objects.filter(source=self.source)]
        channels = []
        if self.source.connector in ConnectionManager.CONNECTOR_PLUGINS:
            plugin  = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
            try:
                source_channels = plugin.get_channels(self.source)
                for channel in source_channels:
                    if channel['id'] not in tracked_channel_ids:
                        channels.append(channel)
            except Exception as e:
                messages.warning(self.request, "Unable to list available channels: %s" % e)
        self.available_channels = sorted(channels, key=lambda c: c['count'], reverse=True)

    def track_channel(self, origin_id):
        if self.source.connector in ConnectionManager.CONNECTOR_PLUGINS:
            plugin  = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
            source_channels = plugin.get_channels(self.source)
            for channel in source_channels:
                if channel['id'] == origin_id:
                    c, created = Channel.objects.get_or_create(origin_id=origin_id, source=self.source, name=channel['name'])
                    if created:
                        messages.success(self.request, "<b>%s</b> has been added to your community tracker, and will appear in the next import" % c.name)

    @login_required
    def as_view(request, community_id, source_id):
        view = Channels(request, community_id, source_id)

        if request.method == 'POST':
            if 'track_channel_id' in request.POST:
                channel_origin_id = request.POST.get('track_channel_id')
                view.track_channel(channel_origin_id)
                return redirect('channels', community_id=community_id, source_id=source_id)
            elif 'remove_channel' in request.POST:
                channel = get_object_or_404(Channel, id=request.POST.get('remove_channel'))
                context = view.context
                context.update({'object_type':"Channel", 'object_name': channel.name, 'object_id': channel.id})
                conversation_count = channel.conversation_set.all().count()
                context['object_dependencies'] = [
                    (conversation_count, pluralize(conversation_count, "conversation")),
                ]
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                channel = get_object_or_404(Channel, id=request.POST.get('object_id'))
                channel_name = channel.name
                channel.delete()
                messages.success(request, "Delete channel: <b>%s</b>" % channel_name)

                return redirect('channels', community_id=community_id, source_id=source_id)


        view.fetch_available_channels()
        return render(request, "savannahv2/channels.html", view.context)