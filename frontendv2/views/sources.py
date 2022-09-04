import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, fields
from django.db.models.fields.related import RelatedField
from django.contrib import messages
from django.http import JsonResponse
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView

class Sources(SavannahView):
    def __init__(self, request, community_id, json=False):
        self._is_json = json
        super().__init__(request, community_id)
        self.active_tab = "sources"

    def all_sources(self):
        return Source.objects.filter(community=self.community).exclude(connector='corm.plugins.null').annotate(channel_count=Count('channel', filter=Q(channel__enabled=True), distinct=True), member_count=Count('contact', distinct=True))

    def _add_sources_message(self):
        if self.request.method == "GET":
            if self.community.source_set.all().count() == 0:
                messages.info(self.request, "Add a source for your community activity using the <div class=\"btn btn-success btn-sm\"><i class=\"fas fa-plus\"></i> Add</div> button below.")
            else:
                super()._add_sources_message()
       
    def available_plugins(self):
        return sorted(ConnectionManager.CONNECTOR_PLUGINS.values(), key=lambda x: x.get_source_type_name().lower())

    @login_required
    def as_view(request, community_id):
        view = Sources(request, community_id)
        if request.method == "POST":
            if 'disable_source' in request.POST:
                source = get_object_or_404(Source, id=request.POST.get('disable_source'))
                source.enabled = False
                source.save()
                return redirect('sources', community_id=community_id)
            if 'enable_source' in request.POST:
                if not view.community.management.can_add_source():
                    view.community.management.upgrade_message(request, "You have reach your maximum number of Sources")
                    return redirect('sources', community_id=community_id)
                source = get_object_or_404(Source, id=request.POST.get('enable_source'))
                source.enabled = True
                source.save()
                return redirect('sources', community_id=community_id)
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
                messages.success(request, "Deleted source: <b>%s</b>" % source_name)
                return redirect('sources', community_id=community_id)
        return render(request, "savannahv2/sources.html", view.context)

    @login_required
    def as_json(request, community_id):
        view = Sources(request, community_id, json=True)
        nodes = list()
        links = list()
        member_map = dict()
        connection_counts = dict()
        connected = set()

        contact_filter = Q(contact__member__last_seen__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        sources = Source.objects.filter(community=view.community).exclude(connector="corm.plugins.null").annotate(contact_count=Count('contact', filter=contact_filter, distinct=True))
        source_node_color = "1cc88a"
        for source in sources:
            if source.contact_count > 0:
                link = reverse('channels', kwargs={'community_id':source.community_id, 'source_id':source.id})
                nodes.append({"id":'s%s'%source.id, "name":"%s (%s)" % (source.name, ConnectionManager.display_name(source.connector)), "link":link, "color":source_node_color, "connections":source.contact_count})
            
        contacts = Contact.objects.filter(source__community=view.community, member__last_seen__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        contacts = contacts.annotate(member_name=F('member__name'), member_role=F('member__role'), tag_count=Count('member__tags'))
        contacts = contacts.order_by('-member__last_seen')[:1000]

        for contact in contacts:
            links.append({"source":'s%s'%contact.source_id, "target":'m%s'%contact.member_id})
            connected.add((contact.source_id, contact.member_id))
            member_map[contact.member_id] = contact
            if contact.member_id not in connection_counts:
                connection_counts[contact.member_id] = 1
            else:
                connection_counts[contact.member_id] += 1

        for member_id, contact in member_map.items():
            tag_color = "1f77b4"
            if contact.tag_count > 0:
                tags = Tag.objects.filter(member__id=member_id)
                if len(tags) > 0:
                    tag_color = tags[0].color
            elif contact.member_role == Member.BOT:
                tag_color = "aeaeae"
            elif contact.member_role == Member.STAFF:
                tag_color = "36b9cc"

            link = reverse('member_profile', kwargs={'member_id':member_id})
            nodes.append({"id":'m%s'%member_id, "name":contact.member_name, "link":link, "color":tag_color, "connections":connection_counts.get(member_id, 0)})
                    
        return JsonResponse({"nodes":nodes, "links":links})

@login_required
def add_source(request, community_id, connector):
    community = get_object_or_404(Community, id=community_id)
    if not community.management.can_add_source():
        community.management.upgrade_message(request, "You have reach your maximum number of Sources")
        return redirect('sources', community_id=community.id)

    plugin = ConnectionManager.CONNECTOR_PLUGINS[connector]
    plugin_add_view = plugin.get_add_view()
    return plugin_add_view(request)

class Channels(SavannahView):
    def __init__(self, request, community_id, source_id):
        super().__init__(request, community_id)
        self.source = get_object_or_404(Source, id=source_id, community=self.community)
        self.active_tab = "sources"
        self.available_channels = []
        self.search_channels = None

    def _add_sources_message(self):
        pass

    def all_channels(self):
        return Channel.objects.filter(source=self.source).annotate(activity_count=Count('activity', distinct=True)).order_by('name')

    def _get_source_channels(self, request):
        channels = []
        if not settings.DEBUG and 'source_channels_cache' in request.session:
            if int(request.session.get('source_channels_source')) == self.source.id and request.session.get('source_channels_expiration') >= datetime.datetime.timestamp(datetime.datetime.utcnow()):
                cached_channels = request.session.get('source_channels_cache')
                if len(cached_channels) > 0:
                    return cached_channels
        if self.source.connector in ConnectionManager.CONNECTOR_PLUGINS:
            plugin  = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
            try:
                channels = plugin.get_channels(self.source)
                request.session['source_channels_search'] = None
                request.session['source_channels_cache'] = channels
                request.session['source_channels_source'] = self.source.id
                request.session['source_channels_expiration'] = datetime.datetime.timestamp(datetime.datetime.utcnow() + datetime.timedelta(minutes=10))
            except Exception as e:
                messages.warning(self.request, "Unable to list available channels: %s" % e)
        return channels

    def fetch_available_channels(self, request):
        tracked_channel_ids = [channel.origin_id for channel in Channel.objects.filter(source=self.source)]
        channels = []
        for channel in self._get_source_channels(request):
            if channel['id'] not in tracked_channel_ids:
                channels.append(channel)
        self.available_channels = sorted(channels, key=lambda c: c['count'], reverse=True)

    def search_available_channels(self, request, text):
        tracked_channel_ids = [channel.origin_id for channel in Channel.objects.filter(source=self.source)]
        channels = []
        plugin = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
        try:
            for channel in plugin.search_channels(self.source, text):
                if channel['id'] not in tracked_channel_ids:
                    channels.append(channel)
            request.session['source_channels_search'] = text
            request.session['source_channels_cache'] = channels
            request.session['source_channels_source'] = self.source.id
            request.session['source_channels_expiration'] = datetime.datetime.timestamp(datetime.datetime.utcnow() + datetime.timedelta(minutes=10))
        except Exception as e:
            messages.warning(self.request, "Unable to list available channels: %s" % e)
        self.available_channels = sorted(channels, key=lambda c: c['count'], reverse=True)

    def track_channel(self, request, origin_id):
        if self.source.connector in ConnectionManager.CONNECTOR_PLUGINS:
            plugin  = ConnectionManager.CONNECTOR_PLUGINS[self.source.connector]
            source_channels = self._get_source_channels(request)
            for channel in source_channels:
                if channel['id'] == origin_id:
                    c, created = Channel.objects.get_or_create(origin_id=origin_id, source=self.source, name=channel['name'])
                    if created:
                        if channel.get('is_private', False):
                            messages.warning(self.request, "<h5><b>WARNING!</b></h5><b>%s</b> is a private channel, but imported conversations will be visible to all of your managers in Savannah.<br/><br/>Delete this channel if it may contain sensitive information you don't want other managers to see." % c.name)
                        else:
                            messages.success(self.request, "<b>%s</b> has been added to your community tracker, and will appear in the next import" % c.name)
                        msg = plugin.get_channel_add_warning(c)
                        if msg is not None:
                            messages.warning(self.request, msg)

    @login_required
    def as_view(request, community_id, source_id):
        view = Channels(request, community_id, source_id)

        if request.method == 'POST':
            if 'track_channel_id' in request.POST:
                channel_origin_id = request.POST.get('track_channel_id')
                view.track_channel(request, channel_origin_id)
                return redirect('channels', community_id=community_id, source_id=source_id)
            if 'disable_channel' in request.POST:
                channel = get_object_or_404(Channel, id=request.POST.get('disable_channel'))
                channel.enabled = False
                channel.save()
                return redirect('channels', community_id=community_id, source_id=source_id)
            if 'enable_channel' in request.POST:
                channel = get_object_or_404(Channel, id=request.POST.get('enable_channel'))
                channel.enabled = True
                channel.save()
                return redirect('channels', community_id=community_id, source_id=source_id)
            if 'remove_channel' in request.POST:
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
                messages.success(request, "Deleted channel: <b>%s</b>" % channel_name)

                return redirect('channels', community_id=community_id, source_id=source_id)

        if 'search_channels' in request.GET:
            if request.GET.get('search_channels', '') == '':
                request.session['source_channels_search'] = None
                view.search_channels = None
            else:
                view.search_available_channels(request, request.GET.get('search_channels'))
                view.search_channels = request.GET.get('search_channels')
        if 'source_channels_search' in request.session and request.session['source_channels_search'] is not None and int(request.session.get('source_channels_source')) == source_id and request.session.get('source_channels_expiration') >= datetime.datetime.timestamp(datetime.datetime.utcnow()):
            view.search_available_channels(request, request.session.get('source_channels_search'))
            view.search_channels = request.session.get('source_channels_search')
        else:
            view.fetch_available_channels(request)
        return render(request, "savannahv2/channels.html", view.context)

from django.http import JsonResponse
@login_required
def tag_channel(request, community_id, source_id):
    source = get_object_or_404(Source, id=source_id)
    if request.method == "POST":
        try:
            channel_id = request.POST.get('channel_id')
            channel = Channel.objects.get(source_id=source_id, id=channel_id)
            tag_id = request.POST.get('tag_select')
            if tag_id == '':
                channel.tag = None
            else:
                tag = Tag.objects.get(community_id=community_id, id=tag_id)
                channel.tag = tag
            channel.save()
            return JsonResponse({'success': True, 'errors':None})
        except Exception as e:
            return JsonResponse({'success':False, 'errors':str(e)})
    return JsonResponse({'success':False, 'errors':'Only POST method supported'})
    
class FileUploadForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ['name', 'uploaded_to', 'source']

    def __init__(self, *args, **kwargs):
        super(FileUploadForm, self).__init__(*args, **kwargs)
        self.fields['other'] = forms.CharField(label="Source Name", required=False)

    def limit_to(self, community):
        self.fields['source'].widget.choices = [(source.id, "%s (%s)" % (source.name, source.connector_name)) for source in Source.objects.filter(community=community)]
        self.fields['source'].widget.choices.insert(0, ('', '-----'))
        self.fields['source'].widget.choices.append(("other", "New Source..."))


class ImportMappingForm(forms.Form):

    def __init__(self, instance, data=None, choices=[]):
        super().__init__(data=data)
        self.instance = instance
        self.choice_list = [('', '-----')] + [(n, n.replace('_', ' ').title()) for n in choices]

        for c in self.instance.columns:
            self.fields[c] = forms.ChoiceField(label=c, choices=self.choice_list, required=False, initial=self.instance.mapping.get(c, ''))

class ImportList(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "sources"

    def all_uploads(self):
        return UploadedFile.objects.filter(community_id=self.community.id)

    def as_view(request, community_id):
        view = ImportList(request, community_id)
        return render(request, 'savannahv2/imports_list.html', view.context)

class ImportInfo(SavannahView):
    def __init__(self, request, community_id, upload_id):
        super().__init__(request, community_id)
        self.active_tab = "sources"
        self.upload_id = upload_id

    @property
    def file(self):
        return UploadedFile.objects.get(id=self.upload_id)

    def as_view(request, community_id, upload_id):
        view = ImportInfo(request, community_id, upload_id)
        return render(request, 'savannahv2/import_info.html', view.context)

class ImportUpload(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "sources"

    def form(self):
        upload_form = FileUploadForm(instance=self.upload)
        upload_form.limit_to(self.community)
        return upload_form
    def as_view(request, community_id):
        view = ImportUpload(request, community_id)
        view.upload = UploadedFile(community=view.community, uploaded_by=request.user, status=UploadedFile.UPLOADED)
        if 'event' in request.GET:
            try:
                view.upload.event = get_object_or_404(Event, community=view.community, id=request.GET.get('event'))
            except Exception as e:
                # print(e)
                messages.error(request, "Unknown event, you can proceed with the import but members will not be added as Attendees")
        if request.method == 'POST':
            form_data = dict(request.POST.items())
            if form_data.get('source') == 'other':
                form_data['source'] = ''
            form = FileUploadForm(data=form_data, files=request.FILES, instance=view.upload)
            form.limit_to(view.community)
            if form.is_valid():
                view.upload = form.save(commit=False)
                if 'event' in request.POST:
                    try:
                        view.upload.event = get_object_or_404(Event, community=view.community, id=request.POST.get('event'))
                    except Exception as e:
                        print(e)
                        messages.error(request, "Unknown event, you can proceed with the import but members will not be added as Attendees")
                if request.POST.get('source') == 'other':
                    view.upload.source = Source.objects.create(community=view.community, name=form.cleaned_data['other'], connector='corm.plugins.null', icon_name='fas fa-file-arrow-up')
                view.upload.save()
                messages.success(request, "File uploaded!")            
                return redirect('import_map', community_id=community_id, upload_id=view.upload.id)
            else:
                view.form = form
                messages.error(request, "Upload failed")
        return render(request, 'savannahv2/import_upload.html', view.context)

class ImportMap(SavannahView):
    def __init__(self, request, community_id, upload_id):
        super().__init__(request, community_id)
        self.upload = get_object_or_404(UploadedFile, id=upload_id)
        self.active_tab = "sources"
        self.target_fields = ['name', 'origin_id', 'email_address', 'phone_number', 'mailing_address', 'avatar_url', 'company', 'tags']

    def form(self):
        mapping_form = ImportMappingForm(instance=self.upload, choices=self.target_fields)
        return mapping_form

    def as_view(request, community_id, upload_id):
        view = ImportMap(request, community_id, upload_id)
        if view.upload.status == UploadedFile.PROCESSING:
            messages.warning(request, "Cannot change field mapping because this import has already started")
            return redirect('import_info', community_id=view.community.id, upload_id=view.upload.id)
        if view.upload.status == UploadedFile.COMPLETE or view.upload.status == UploadedFile.FAILED:
            messages.warning(request, "Cannot change field mapping because this import has already finished")
            return redirect('import_info', community_id=view.community.id, upload_id=view.upload.id)
        if view.upload.status == UploadedFile.CANCELED:
            messages.warning(request, "Cannot change field mapping because this import has been canceled")
            return redirect('import_info', community_id=view.community.id, upload_id=view.upload.id)

        if request.method == 'POST':
            form = ImportMappingForm(data=request.POST, instance=view.upload, choices=view.target_fields)
            if form.is_valid():
                view.upload.mapping = dict()
                for src, dst in form.cleaned_data.items():
                    view.upload.mapping[src] = dst
                # view.upload.save()
                if view.upload.source and not 'origin_id' in form.cleaned_data.values():
                    messages.error(request, "You must map a field to Origin ID when importing to a Source")
                    return render(request, 'savannahv2/import_map.html', view.context)
                if not view.upload.source and 'origin_id' in form.cleaned_data.values():
                    messages.error(request, "You cannot map a field to Origin ID because you haven't assigned a Source")
                    return render(request, 'savannahv2/import_map.html', view.context)
                view.upload.status = UploadedFile.PENDING
                view.upload.save()
                messages.success(request, "Your upload will begin shortly")            
                return redirect('import_info', community_id=community_id, upload_id=view.upload.id)
            else:
                view.form = form
                messages.error(request, "Mapping failed")
        return render(request, 'savannahv2/import_map.html', view.context)

class ImportCancel(SavannahView):
    def __init__(self, request, community_id, upload_id):
        super().__init__(request, community_id)
        self.upload = get_object_or_404(UploadedFile, id=upload_id)

    def as_view(request, community_id, upload_id):
        view = ImportCancel(request, community_id, upload_id)
        if view.upload.status == UploadedFile.COMPLETE or view.upload.status == UploadedFile.FAILED:
            messages.warning(request, "Cannot cancel an import that is already finished")
            return redirect('import_info', community_id=view.community.id, upload_id=view.upload.id)

        if request.method == 'POST':
            if 'cancel_import' in request.POST:
                context = view.context
                context.update({'action_name':'Cancel', 'object_type':"Import", 'object_name': view.upload.name, 'object_id': view.upload.id})
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                view.upload.status = UploadedFile.CANCELED
                view.upload.save()
                messages.success(request, "Canceled import: <b>%s</b>" % view.upload.name)

                return redirect('import_list', community_id=community_id)
        return redirect('import_list', community_id=community_id)
