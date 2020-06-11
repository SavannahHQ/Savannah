import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django import forms
from django.http import JsonResponse

from corm.models import *
from corm.connectors import ConnectionManager
from frontendv2.views import SavannahView, SavannahFilterView

class Members(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "members"
        self._membersChart = None
        self._tagsChart = None
        self._sourcesChart = None
    
    @property
    def all_members(self):
        members = Member.objects.filter(community=self.community)
        if self.tag:
            members =members.filter(tags=self.tag)
        if self.role:
            members =members.filter(role=self.role)
        members = members.annotate(note_count=Count('note'), tag_count=Count('tags'))
        return members

    @property
    def new_members(self):
        members = Member.objects.filter(community=self.community)
        if self.tag:
            members = members.filter(tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)
        return members.order_by("-first_seen")[:10]

    @property
    def recently_active(self):
        members = Member.objects.filter(community=self.community)
        convo_filter = Q(speaker_in__timestamp__isnull=False)
        if self.tag:
            convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)
            
        members = members.annotate(last_active=Max('speaker_in__timestamp', filter=convo_filter))
        actives = dict()
        for m in members:
            if m.last_active is not None:
                actives[m] = m.last_active
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def most_active(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        convo_filter = Q(speaker_in__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))
        if self.tag:
            convo_filter = convo_filter & Q(speaker_in__tags=self.tag)
        if self.role:
            members = members.filter(role=self.role)

        members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter))
        for m in members:
            if m.conversation_count > 0:
                activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:20]

    @property
    def most_connected(self):
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

    def getMembersChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()
            total = 0
            members = Member.objects.filter(community=self.community)
            if self.tag:
                members = members.filter(tags=self.tag)
            if self.role:
                members = members.filter(role=self.role)
            members = members.order_by("first_seen")
            for m in members:
                total += 1
                month = str(m.first_seen)[:7]
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        return [month for month in months[-12:]]

    @property
    def members_chart_counts(self):
        (months, counts) = self.getMembersChart()
        return [counts[month] for month in months[-12:]]

    def getTagsChart(self):
        if not self._tagsChart:
            tags = list()
            counts = dict()
            total = 0
            tags = Tag.objects.filter(community=self.community)
            if self.role:
                tags = tags.annotate(member_count=Count('member', filter=Q(member__role=self.role))).order_by('-member_count')
            else:
                tags = tags.annotate(member_count=Count('member')).order_by('-member_count')
            for t in tags:
                counts[t] = t.member_count
            self._tagsChart = [('#'+tag.name, count, '#'+tag.color) for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._tagsChart) > 8:
                other_count = sum([count for tag, count, color in self._tagsChart[7:]])
                self._tagsChart = self._tagsChart[:7]
                self._tagsChart.append(("Other", other_count, "#efefef"))
        return self._tagsChart

    @property
    def tag_names(self):
        chart = self.getTagsChart()
        return [tag[0] for tag in chart]

    @property
    def tag_counts(self):
        chart = self.getTagsChart()
        return [tag[1] for tag in chart]

    @property
    def tag_colors(self):
        chart = self.getTagsChart()
        return [tag[2] for tag in chart]

    def getSourcesChart(self):
        if not self._sourcesChart:
            counts = dict()
            other_count = 0
            identity_filter = Q()
            if self.tag:
                identity_filter = identity_filter & Q(contact__member__tags=self.tag)
            if self.role:
                identity_filter = identity_filter & Q(contact__member__role=self.role)
            sources = Source.objects.filter(community=self.community).annotate(identity_count=Count('contact', filter=identity_filter))
            for source in sources:
                if source.identity_count == 0:
                    continue
                counts["%s (%s)" % (source.name, ConnectionManager.display_name(source.connector))] = source.identity_count
            self._sourcesChart = [(source, count) for source, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._sourcesChart) > 8:
                other_count += sum([count for tag, count in self._sourcesChart[7:]])
            if other_count > 0:
                self._sourcesChart = self._sourcesChart[:7]
                self._sourcesChart.append(("Other", other_count, "#efefef"))
        return self._sourcesChart

    @property
    def source_names(self):
        chart = self.getSourcesChart()
        return [source[0] for source in chart]

    @property
    def source_counts(self):
        chart = self.getSourcesChart()
        return [source[1] for source in chart]

    @login_required
    def as_view(request, community_id):
        members = Members(request, community_id)

        return render(request, 'savannahv2/members.html', members.context)


class AllMembers(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "members"

        self.RESULTS_PER_PAGE = 25
        self.community = get_object_or_404(Community, id=community_id)

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
    def all_members(self):
        members = Member.objects.filter(community=self.community)
        if self.search:
            members = members.filter(Q(name__icontains=self.search) | Q(contact__detail__icontains=self.search))

        if self.tag:
            members = members.filter(tags=self.tag)

        if self.role:
            members = members.filter(role=self.role)

        members = members.annotate(note_count=Count('note'), tag_count=Count('tags'))
        self.result_count = members.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return members[start:start+self.RESULTS_PER_PAGE]

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return pages+1

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return [page+1 for page in range(pages+1)]

    @login_required
    def as_view(request, community_id):
        view = AllMembers(request, community_id)

        return render(request, 'savannahv2/all_members.html', view.context)

class MemberProfile(SavannahFilterView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

        self.RESULTS_PER_PAGE = 100
        self._engagementChart = None
        self._channelsChart = None
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

    @property
    def all_conversations(self):
        conversations = Conversation.objects.filter(channel__source__community=self.member.community, participants=self.member)
        if self.tag:
            conversations = conversations.filter(tags=self.tag)
        if self.role:
            conversations = conversations.filter(participants__role=self.role)

        conversations = conversations.annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        return conversations[:20]

    @property
    def all_contributions(self):
        contributions = Contribution.objects.filter(community=self.member.community, author=self.member).annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        if self.tag:
            contributions = contributions.filter(tags=self.tag)
        if self.role:
            contributions = contributions.filter(author__role=self.role)

        contributions = contributions.annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        return contributions[:10]

    def getEngagementChart(self):
        if not self._engagementChart:
            conversations_counts = dict()
            activity_counts = dict()
            conversations = conversations = Conversation.objects.filter(channel__source__community=self.member.community, participants=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90))
            if self.tag:
                conversations = conversations.filter(tags=self.tag)
            if self.role:
                conversations = conversations.filter(speaker__role=self.role)

            conversations = conversations.order_by("timestamp")
            for c in conversations:
                month = str(c.timestamp)[:10]
                if month not in conversations_counts:
                    conversations_counts[month] = 1
                else:
                    conversations_counts[month] += 1

            activity = Contribution.objects.filter(community=self.member.community, author=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90))
            if self.tag:
                activity = activity.filter(tags=self.tag)
            if self.role:
                activity = activity.filter(author__role=self.role)

            activity = activity.order_by("timestamp")

            for a in activity:
                month = str(a.timestamp)[:10]
                if month not in activity_counts:
                    activity_counts[month] = 1
                else:
                    activity_counts[month] += 1
            self._engagementChart = (conversations_counts, activity_counts)
        return self._engagementChart
        
    @property
    def engagement_chart_months(self):
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [str(day)[:10] for day in date_list]

    @property
    def engagement_chart_conversations(self):
        (conversations_counts, activity_counts) = self.getEngagementChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [conversations_counts.get(str(day)[:10], 0) for day in date_list]

    @property
    def engagement_chart_activities(self):
        (conversations_counts, activity_counts) = self.getEngagementChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [activity_counts.get(str(day)[:10], 0) for day in date_list]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            from_colors = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc']
            next_color = 0
            channels = Channel.objects.filter(source__community=self.member.community)
            convo_filter = Q(conversation__participants=self.member, conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
            if self.role:
                convo_filter = convo_filter & Q(conversation__speaker__role=self.role)

            channels = channels.annotate(conversation_count=Count('conversation', filter=convo_filter))
            channels = channels.annotate(source_icon=F('source__icon_name'), source_connector=F('source__connector'), color=F('tag__color'))
            for c in channels:
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

    @login_required
    def as_view(request, member_id):
        view = MemberProfile(request, member_id)

        return render(request, 'savannahv2/member_profile.html', view.context)

from django.http import JsonResponse
@login_required
def tag_member(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        tag_ids = request.POST.getlist('tag_select')
        tags = Tag.objects.filter(community=member.community, id__in=tag_ids)
        member.tags.set(tags)
    return JsonResponse({'success': True, 'errors':None})

class MemberEditForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['name', 'role', 'email_address', 'phone_number', 'mailing_address']
        widgets = {
            'mailing_address': forms.Textarea(attrs={'cols': 40, 'rows': 6}),
        }

class MemberEdit(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

    @property
    def form(self):
        if self.request.method == 'POST':
            return MemberEditForm(instance=self.member, data=self.request.POST)
        else:
            return MemberEditForm(instance=self.member)

    @login_required
    def as_view(request, member_id):
        view = MemberEdit(request, member_id)
        
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('member_profile', member_id=member_id)

        return render(request, 'savannahv2/member_edit.html', view.context)

class MemberMerge(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

        self.RESULTS_PER_PAGE = 25
        self.member = get_object_or_404(Member, id=member_id)
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'search' in request.GET:
            self.search = request.GET.get('search', "").lower()
        else:
            self.search = None

    @property
    def possible_matches(self):
        matches = Member.objects.filter(community=self.member.community)
        if self.search:
            return matches.filter(Q(name__icontains=self.search)|Q(contact__detail__icontains=self.search)).exclude(id=self.member.id).distinct()
        else:
            same_contact = [contact.detail for contact in self.member.contact_set.all()]
            contact_matches = matches.filter(Q(contact__detail__in=same_contact))

            similar_contact = [name for name in self.member.name.split(" ") if len(name) > 2]
            if len(similar_contact) == 0:
                return []
            elif len(similar_contact) > 1:
                similar_matches = matches.filter(~Q(contact__detail__in=same_contact) & reduce(operator.or_, (Q(contact__detail__icontains=name) for name in similar_contact)))
            elif len(similar_contact) == 1:
                similar_matches = matches.filter(~Q(contact__detail__in=same_contact) & Q(contact__detail__icontains=similar_contact[0]))
            contact_matches = contact_matches.exclude(id=self.member.id).distinct()
            similar_matches = similar_matches.exclude(id=self.member.id).distinct()[:20]
            return list(contact_matches) + list(similar_matches)

    @login_required
    def as_view(request, member_id):
        view = MemberMerge(request, member_id)
        
        if request.method == 'POST':
            merge_with = get_object_or_404(Member, id=request.POST.get('merge_with'))
            view.member.merge_with(merge_with)
            return redirect('member_merge', member_id=member_id)

        return render(request, 'savannahv2/member_merge.html', view.context)