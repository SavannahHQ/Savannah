import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, Avg
from django.db.models.functions import Trunc, Lower
from django import forms
from django.http import JsonResponse
from django.contrib import messages

from corm.models import *
from corm.connectors import ConnectionManager
from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import PieChart
from savannah.utils import safe_int
from frontendv2 import colors as savannah_colors
from frontendv2.models import PublicDashboard

class Members(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "members"
        self._membersChart = None
        self._tagsChart = None
        self._sourcesChart = None
        self._tagsChart = None
        self._rolesChart = None
        self._dauPercent = None

    def suggestion_count(self):
        return SuggestMemberMerge.objects.filter(community=self.community, status__isnull=True).count()

    @property
    def all_members(self):
        members = Member.objects.filter(community=self.community)
        if self.member_company:
            members =members.filter(company=self.member_company)
        if self.member_tag:
            members =members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)
        members = members.annotate(note_count=Count('note'), tag_count=Count('tags'))
        return members

    @property
    def new_members(self):
        members = Member.objects.filter(community=self.community)
        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)
        members = members.filter(first_seen__gte=self.rangestart, first_seen__lte=self.rangeend)
        members = members.prefetch_related('tags')

        return members.order_by("-first_seen")[:10]

    @property
    def recently_active(self):
        members = Member.objects.filter(community=self.community)
        if self.member_company:
            members = members.filter(company=self.member_company)
        if self.member_tag:
            members = members.filter(tags=self.member_tag)
        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)
            
        members = members.annotate(last_active=Max('activity__timestamp', filter=Q(activity__timestamp__isnull=False)))
        members = members.filter(last_active__gte=self.rangestart, last_active__lte=self.rangeend)
        members = members.prefetch_related('tags')
 
        return members.order_by('-last_active')[:10]

    def getMembersChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()
            monthly_active = dict()
            total = 0
            members = Member.objects.filter(community=self.community)
            if self.member_company:
                members = members.filter(company=self.member_company)
            if self.member_tag:
                members = members.filter(tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    members = members.exclude(role=self.role)
                else:
                    members = members.filter(role=self.role)

            seen = members.annotate(month=Trunc('first_seen', self.trunc_span)).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
            for m in seen:
                total += 1
                month = self.trunc_date(m['month'])

                if month not in months:
                    months.append(month)
                counts[month] = m['member_count']

            active = members.annotate(month=Trunc('activity__timestamp', self.trunc_span)).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
            for a in active:
                if a['month'] is not None:
                    month = self.trunc_date(a['month'])

                    if month not in months:
                        months.append(month)
                    monthly_active[month] = a['member_count']
            self._membersChart = (sorted(months), counts, monthly_active)
        return self._membersChart

    @property
    def members_chart_months(self):
        (months, counts, monthly_active) = self.getMembersChart()
        return self.timespan_chart_keys(months)

    @property
    def members_chart_counts(self):
        (months, counts, monthly_active) = self.getMembersChart()
        return [counts.get(month, 0) for month in self.timespan_chart_keys(months)]

    @property
    def members_chart_monthly_active(self):
        (months, counts, monthly_active) = self.getMembersChart()
        return [monthly_active.get(month, 0) for month in self.timespan_chart_keys(months)]

    @property
    def members_chart_monthly_returning(self):
        (months, joined, active) = self.getMembersChart()
        data = []
        month_keys = self.timespan_chart_keys(months)
        for i, month in enumerate(month_keys):
            returned = active.get(month, 0) - joined.get(month, 0)
            if returned < 0:
                returned = 0
            data.append(returned)
        return data

    @property 
    def member_count(self):
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

        members = members.annotate(activity_count=Count('activity', filter=Q(activity__timestamp__gte=self.rangestart, activity__timestamp__lte=self.rangeend))).filter(activity_count__gt=0)
        return members.count()

    @property
    def conversations_per_member(self):
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

        members = members.annotate(activity_count=Count('activity', filter=Q(activity__timestamp__gte=self.rangestart, activity__timestamp__lte=self.rangeend))).filter(activity_count__gt=0)
        member_count = members.count()

        convo_count = Conversation.objects.filter(speaker__in=members, timestamp__gte=self.rangestart, timestamp__lte=self.rangeend).count()
        if member_count > 0:
            return convo_count / member_count
        else:
            return 0

    @property
    def dau_to_mau(self):
        if not self._dauPercent:
            members = Member.objects.filter(community=self.community)
            if self.member_company:
                members = members.filter(company=self.member_company)
            if self.member_tag:
                members = members.filter(tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    members = members.exclude(role=self.role)
                else:
                    members = members.filter(role=self.role)
            if self.source:
                members = members.filter(contact__source=self.source)
                
            members = members.annotate(activity_count=Count('activity', filter=Q(activity__timestamp__gte=self.rangestart, activity__timestamp__lte=self.rangeend))).filter(activity_count__gt=0)

            daily_active = members.annotate(day=Trunc('activity__timestamp', 'day')).values('day').annotate(member_count=Count('id', distinct=True)).order_by('day')
            daily = daily_active.aggregate(avg=Avg('member_count'))

            monthly_active = members.annotate(month=Trunc('activity__timestamp', 'month')).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
            monthly = monthly_active.aggregate(avg=Avg('member_count'))

            if monthly['avg'] and monthly['avg'] > 0:
                self._dauPercent = 100 * (daily['avg'] / monthly['avg'])
            else:
                self._dauPercent = 0
        return self._dauPercent

    def sources_chart(self):
        if not self._sourcesChart:
            counts = dict()
            other_count = 0
            identity_filter = Q(contact__member__first_seen__gte=self.rangestart, contact__member__last_seen__lte=self.rangeend)
            if self.member_company:
                identity_filter = identity_filter & Q(contact__member__company=self.member_company)
            if self.member_tag:
                identity_filter = identity_filter & Q(contact__member__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    identity_filter = identity_filter & ~Q(contact__member__role=self.role)
                else:
                    identity_filter = identity_filter & Q(contact__member__role=self.role)
            if self.source:
                identity_filter = identity_filter & Q(contact__source=self.source)
            sources = Source.objects.filter(community=self.community).annotate(identity_count=Count('contact', filter=identity_filter))
            for source in sources:
                if source.identity_count == 0:
                    continue
                counts[source] = source.identity_count

            self._sourcesChart = PieChart("sourcesChart", title="Member Sources", limit=8)
            for source, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                if source.connector == 'corm.plugins.api':
                    self._sourcesChart.add(source.name, count)
                elif Source.objects.filter(community=self.community, connector=source.connector).count() == 1:
                    self._sourcesChart.add(ConnectionManager.display_name(source.connector), count)
                else:
                    self._sourcesChart.add("%s (%s)" % (ConnectionManager.display_name(source.connector), source.name), count)
        self.charts.add(self._sourcesChart)
        return self._sourcesChart

    def rolesChart(self):
        if not self._rolesChart:
            counts = dict()
            colors = {
                Member.COMMUNITY: savannah_colors.MEMBER.COMMUNITY,
                Member.STAFF: savannah_colors.MEMBER.STAFF,
                Member.BOT: savannah_colors.MEMBER.BOT
            }
            members = Member.objects.filter(community=self.community)

            if self.member_company:
                members = members.filter(company=self.member_company)
            if self.member_tag:
                members = members.filter(tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    members = members.exclude(role=self.role)
                else:
                    members = members.filter(role=self.role)

            members = members.annotate(activity_count=Count('activity', filter=Q(activity__timestamp__gte=self.rangestart, activity__timestamp__lte=self.rangeend))).filter(activity_count__gt=0)

            for m in members:
                if m.role in counts:
                    counts[m.role] += 1
                else:
                    counts[m.role] = 1
            self._rolesChart = PieChart("rolesChart", title="Members by Role")
            for role, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                self._rolesChart.add(Member.ROLE_NAME[role], count, colors[role])
        self.charts.add(self._rolesChart)
        return self._rolesChart

    def tagsChart(self):
        if not self._tagsChart:
            counts = dict()
            tags = Tag.objects.filter(community=self.community)
            member_filter = Q(member__community=self.community, member__activity__timestamp__gte=self.rangestart, member__activity__timestamp__lte=self.rangeend)
            if self.member_company:
                member_filter = member_filter & Q(member__company=self.member_company)
            if self.member_tag:
                member_filter = member_filter & Q(member__tags=self.member_tag)
            if self.role:
                if self.role == Member.BOT:
                    member_filter = member_filter & ~Q(member__role=self.role)
                else:
                    member_filter = member_filter & Q(member__role=self.role)

            tags = tags.annotate(member_count=Count('member', distinct=True, filter=member_filter))
            tags = tags.filter(member_count__gt=0).order_by('-member_count')

            self._tagsChart = PieChart("tagsChart", title="Members by Tag", limit=12)
            for tag in tags:
                self._tagsChart.add(tag.name, tag.member_count, tag.color)
        self.charts.add(self._tagsChart)
        return self._tagsChart

    @login_required
    def as_view(request, community_id):
        members = Members(request, community_id)
        return render(request, 'savannahv2/members.html', members.context)

    @login_required
    def publish(request, community_id):
        if 'cancel' in request.GET:
            return redirect('members', community_id=community_id)
            
        members = Members(request, community_id)
        return members.publish_view(request, PublicDashboard.MEMBERS, 'public_members')

    def public(request, dashboard_id):
        dashboard = get_object_or_404(PublicDashboard, id=dashboard_id)
        members = Members(request, dashboard.community.id)
        context = dashboard.apply(members)
        if not request.user.is_authenticated:
            dashboard.count()
        return render(request, 'savannahv2/public/members.html', context)

class AllMembers(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "members"

        self.RESULTS_PER_PAGE = 25
        self.community = get_object_or_404(Community, id=community_id)

        self.sort_by = request.session.get("sort_members", "name")
        if 'sort' in request.GET and request.GET.get('sort') in ('name', '-name', 'company', '-company', 'first_seen', '-first_seen', 'last_seen', '-last_seen'):
            self.sort_by = request.GET.get('sort') 
            request.session['sort_members'] = self.sort_by

        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1

        if 'search' in request.GET:
            self.search = request.GET.get('search', "").lower().strip()
        else:
            self.search = None
        self.result_count = 0
    
    @property
    def all_members(self):
        members = Member.objects.filter(community=self.community)
        if self.search:
            members = members.filter(Q(name__icontains=self.search) | Q(company__name__icontains=self.search) | Q(email_address__icontains=self.search) | Q(contact__detail__icontains=self.search) | Q(contact__email_address__icontains=self.search) | Q(note__content__icontains=self.search))

        if self.member_company:
            members = members.filter(company=self.member_company)

        if self.member_tag:
            members = members.filter(tags=self.member_tag)

        if self.role:
            if self.role == Member.BOT:
                members = members.exclude(role=self.role)
            else:
                members = members.filter(role=self.role)

        if self.timespan < 365:
            members = members.filter(last_seen__gte=self.rangestart, last_seen__lte=self.rangeend)
        if self.sort_by == 'name':
            members = members.order_by(Lower('name'))
        elif self.sort_by == '-name':
            members = members.order_by(Lower('name').desc())
        else:
            members = members.order_by(self.sort_by)

        members = members.annotate(note_count=Count('note'), tag_count=Count('tags'))
        self.result_count = members.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return members[start:start+self.RESULTS_PER_PAGE]

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

    @login_required
    def as_view(request, community_id):
        view = AllMembers(request, community_id)

        return render(request, 'savannahv2/all_members.html', view.context)

class MemberNoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['content', 'tags']

   
class MemberProfile(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"
        
    @property
    def has_merge_history(self):
        return MemberMergeRecord.objects.filter(community=self.member.community, merged_with=self.member).count() > 0
        
    @property
    def is_watched(self):
        return MemberWatch.objects.filter(manager=self.request.user, member=self.member).count() > 0
        
    @property 
    def member_levels(self):
        return MemberLevel.objects.filter(community=self.community, member=self.member).order_by('-project__default_project', '-level', 'timestamp')

    def open_tasks(self):
        return Task.objects.filter(stakeholders=self.member, done__isnull=True)

    @property
    def all_gifts(self):
        return Gift.objects.filter(community=self.community, member=self.member)

    @property
    def all_contributions(self):
        contributions = Contribution.objects.filter(community=self.member.community, author=self.member).annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')

        contributions = contributions.annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        return contributions[:10]

    @property 
    def recent_connections(self):
        connections = MemberConnection.objects.filter(from_member=self.member).order_by('-last_connected')[:10]
        connections.select_related('to_member').prefetch_related('to_member__tags')
        return connections

    @property 
    def top_connections(self):
        connections = MemberConnection.objects.filter(from_member=self.member).order_by('-connection_count')[:10]
        connections.select_related('to_member').prefetch_related('to_member__tags')
        return connections

    @login_required
    def as_view(request, member_id):
        view = MemberProfile(request, member_id)
        if request.method == 'POST':
            if 'delete_note' in request.POST:
                note = get_object_or_404(Note, id=request.POST.get('delete_note'))
                context = view.context
                context.update({
                    'object_type':"Note", 
                    'object_name': str(note), 
                    'object_id': note.id,
                })
                return render(request, "savannahv2/delete_confirm.html", context)
            elif 'delete_confirm' in request.POST:
                note = get_object_or_404(Note, id=request.POST.get('object_id'))
                note.delete()
                messages.success(request, "Note deleted")

                return redirect('member_profile', member_id=member_id)
        return render(request, 'savannahv2/member_profile.html', view.context)

class MemberActivity(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

        self.RESULTS_PER_PAGE = 20
        self._engagementChart = None
        self._sourcesChart = None
        self._channelsChart = None
        self._tagsChart = None
        try:
            self.page = int(request.GET.get('page', 1))
        except:
            self.page = 1
        self.tag = None
        self.member_tag = None
        self.role = None
        
    @property
    def is_watched(self):
        return MemberWatch.objects.filter(manager=self.request.user, member=self.member).count() > 0
        
    @property
    def all_activity(self):
        activity = Activity.objects.filter(channel__source__community=self.member.community, member=self.member)
        self.result_count = activity.count()
        activity = activity.annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return activity[start:start+self.RESULTS_PER_PAGE]

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

    def getEngagementChart(self):
        if not self._engagementChart:
            conversations_counts = dict()
            activity_counts = dict()
            conversations = conversations = Conversation.objects.filter(channel__source__community=self.member.community, speaker=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90))
            if self.tag:
                conversations = conversations.filter(tags=self.tag)
            if self.role:
                if self.role == Member.BOT:
                    conversations = conversations.exclude(speaker__role=self.role)
                else:
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
                if self.role == Member.BOT:
                    activity = activity.exclude(author__role=self.role)
                else:
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

    def channels_chart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            from_colors = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc']
            next_color = 0
            channels = Channel.objects.filter(source__community=self.member.community)
            convo_filter = Q(conversation__speaker=self.member, conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))
            if self.tag:
                convo_filter = convo_filter & Q(conversation__tags=self.tag)
            if self.role:
                if self.role == Member.BOT:
                    convo_filter = convo_filter & ~Q(conversation__speaker__role=self.role)
                else:
                    convo_filter = convo_filter & Q(conversation__speaker__role=self.role)

            channels = channels.annotate(conversation_count=Count('conversation', filter=convo_filter))
            channels = channels.annotate(source_icon=F('source__icon_name'), source_connector=F('source__connector'), color=F('tag__color'))
            for c in channels:
                if c.conversation_count == 0:
                    continue
                counts[c] = c.conversation_count 

            self._channelsChart = PieChart("channelsChart", title="Conversations by Channel", limit=8)
            for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                self._channelsChart.add("%s (%s)" % (channel.name, ConnectionManager.display_name(channel.source_connector)), count, channel.color)
        self.charts.add(self._channelsChart)
        return self._channelsChart

    def sources_chart(self):
        source_names = dict()
        if not self._sourcesChart:
            sources = list()
            counts = dict()
            sources = Source.objects.filter(community=self.member.community)
            convo_filter = Q(channel__conversation__speaker=self.member, channel__conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))

            sources = sources.annotate(conversation_count=Count('channel__conversation', filter=convo_filter)).filter(conversation_count__gt=0).order_by('-conversation_count')
 
            self._sourcesChart = PieChart("sourcesChart", title="Conversations by Source", limit=8)
            for source in sources:
                self._sourcesChart.add("%s (%s)" % (source.name, ConnectionManager.display_name(source.connector)), source.conversation_count)

        self.charts.add(self._sourcesChart)
        return self._sourcesChart

    def tags_chart(self):
        if not self._tagsChart:
            counts = dict()
            tags = Tag.objects.filter(community=self.community)
            convo_filter = Q(conversation__speaker=self.member, conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))

            tags = tags.annotate(conversation_count=Count('conversation', filter=convo_filter))

            for t in tags:
                counts[t] = t.conversation_count
            self._tagsChart = PieChart("tagsChart", title="Conversations by Tag", limit=12)
            for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True):
                if count > 0:
                    self._tagsChart.add(tag.name, count, tag.color)
        self.charts.add(self._tagsChart)
        return self._tagsChart

    @login_required
    def as_view(request, member_id):
        view = MemberActivity(request, member_id)
        return render(request, 'savannahv2/member_activity.html', view.context)

class ContributionPromotionForm(forms.ModelForm):
    class Meta:
        model = Contribution
        fields = ['title', 'contribution_type', 'location']

    def limit_to(self, community):
        current_source = None
        choices = [(None, '--------')]
        for contrib_type in ContributionType.objects.filter(community=community, source__isnull=False).select_related('source').order_by(Lower('source__connector')):
            source_name = '%s (%s)' % (contrib_type.source.connector_name, contrib_type.source.name)
            if source_name != current_source:
                current_source = source_name
                choices.append((source_name, []))
            choices[-1][1].append((contrib_type.id, contrib_type.name))
        self.fields['contribution_type'].widget.choices = choices

class PromoteToContribution(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

    @property
    def form(self):
        new_contrib = Contribution(community=self.community, author=self.conversation.speaker, channel=self.conversation.channel, timestamp=self.conversation.timestamp, location=self.conversation.location)
        if self.request.method == 'POST':
            form = ContributionPromotionForm(instance=new_contrib, data=self.request.POST)
        else:
            form = ContributionPromotionForm(instance=new_contrib)
        form.limit_to(self.community)
        return form

    @login_required
    def as_view(request, member_id):
        view = PromoteToContribution(request, member_id)

        if request.GET.get('conversation_id', None) is None:
            messages.error(request, "No conversation was chosen to be promoted to a contribution.")
            return redirect('member_activity', member_id=member_id)

        try:
            view.conversation = Conversation.objects.get(speaker__community=view.community, id=request.GET.get('conversation_id'))
        except:
            messages.error(request, "Could not find the conversation.")
            return redirect('member_activity', member_id=member_id)

        if request.method == 'POST':
            if view.form.is_valid():
                contrib = view.form.save()
                activity = view.conversation.activity
                activity.contribution = contrib
                activity.short_description = contrib.contribution_type.name
                activity.icon_name = 'fas fa-shield-alt'
                activity.save()
                messages.success(request, "Converastion has been promoted to a Contribution.")
                return redirect('member_activity', member_id=member_id)

        return render(request, 'savannahv2/promote_to_contribution.html', view.context)

class MemberMergeHistory(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

    def all_merges(self):
        return MemberMergeRecord.objects.filter(community=self.member.community, merged_with=self.member).order_by('-merged_date')

    @login_required
    def as_view(request, member_id):
        view = MemberMergeHistory(request, member_id)
        if request.method == 'POST':
            if 'restore_member' in request.POST:
                record = get_object_or_404(MemberMergeRecord, id=request.POST.get('restore_member'))
                # TODO Redirect to confirmation page
                context = view.context
                context.update({
                    'object_type':"Member", 
                    'object_name': record.name, 
                    'object_id': record.id,
                    'warning_msg': 'This will also revert changes to the current member that were the result of this merge',
                })
                return render(request, "savannahv2/restore_confirm.html", context)
            elif 'restore_confirm' in request.POST:
                record = get_object_or_404(MemberMergeRecord, id=request.POST.get('object_id'))
                new_member = record.restore()
                messages.success(request, "Member restored")

                return redirect('member_profile', member_id=new_member.id)
        return render(request, 'savannahv2/merge_history.html', view.context)

from django.http import JsonResponse
@login_required
def add_note(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        note_id = safe_int(request.POST.get('note_id'), 0)
        note_content = request.POST.get('note_content')
        if note_content is None or note_content == '':
            return JsonResponse({'success': False, 'errors':'No content provided'}, status=400)
        if note_id != 0:
            note = Note.objects.get(id=note_id)
            note.content=note_content
            note.save()
        else:
            note = Note.objects.create(member=member, author=request.user, content=note_content)
        return JsonResponse({'success': True, 'errors':None, 'note_id': note.id})
    return JsonResponse({'success': False, 'errors':'Only POST method supported'}, status=405)

@login_required
def tag_member(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        tag_ids = request.POST.getlist('tag_select')
        tags = Tag.objects.filter(community=member.community, id__in=tag_ids)
        member.tags.set(tags)
        return JsonResponse({'success': True, 'errors':None})
    return JsonResponse({'success': False, 'errors':'Only POST method supported'}, status=405)

@login_required
def followup_on_member(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        days = request.POST.get('days', "1")
        custom = request.POST.get('custom')
        if custom:
            due = datetime.datetime.strptime(custom, '%Y-%m-%d')
        else:
            try:
                due = datetime.datetime.utcnow() + datetime.timedelta(days=int(days))
            except:
                messages.error(request, "Bad follow-up duration: %s" % days)
                pass
        followup = Task.objects.create(owner=request.user, community=member.community, name="Follow up with %s" % member.name, due=due, project=member.community.default_project)
        followup.stakeholders.add(member)
        messages.success(request, "Follow-up task created for %s" % due.date())
    return redirect('member_profile', member_id=member_id)

@login_required
def watch_member(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'watch':
            try:
                last_convo = Conversation.objects.filter(speaker=member).order_by('-timestamp')[0]
                MemberWatch.objects.get_or_create(manager=request.user, member=member, last_seen=last_convo.timestamp, last_channel=last_convo.channel)
            except:
                MemberWatch.objects.get_or_create(manager=request.user, member=member)
            messages.success(request, "You will be notified whenever %s is active in your community" % member.name)
        else:
            MemberWatch.objects.filter(manager=request.user, member=member).delete()
            messages.warning(request, "You will no longer be notified if %s is active in your community" % member.name)
    return redirect('member_profile', member_id=member_id)

class MemberEditForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['name', 'company', 'role', 'email_address', 'avatar_url', 'phone_number', 'mailing_address']
        widgets = {
            'mailing_address': forms.Textarea(attrs={'cols': 40, 'rows': 6}),
        }

    def limit_to(self, community):
        self.fields['company'].widget.choices = [('', '-----')] + [(company.id, company.name) for company in Company.objects.filter(community=community).order_by(Lower('name'))]


class MemberEdit(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super().__init__(request, self.member.community_id)
        self.active_tab = "members"

    @property
    def identities(self):
        return Contact.objects.filter(member=self.member).all()

    @property
    def form(self):
        if self.request.method == 'POST':
            form = MemberEditForm(instance=self.member, data=self.request.POST)
        else:
            form = MemberEditForm(instance=self.member)
        form.limit_to(self.community)
        return form

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

class GiftForm(forms.ModelForm):
    class Meta:
        model = Gift
        fields = ['gift_type', 'sent_date', 'reason', 'tracking', 'received_date']
        widgets = {
            'sent_date': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
            'received_date': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }
    def __init__(self, *args, **kwargs):
        super(GiftForm, self).__init__(*args, **kwargs)
        self.fields['sent_date'].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields['received_date'].input_formats = ["%Y-%m-%dT%H:%M"]

class GiftManager(SavannahView):
    def __init__(self, request, member_id, gift_id=None):
        self.member = get_object_or_404(Member, id=member_id)
        super(GiftManager, self).__init__(request, self.member.community_id)
        self.active_tab = "members"
        if gift_id:
            self.gift = get_object_or_404(Gift, id=gift_id)
        else:
            self.gift = Gift(community=self.community, member=self.member, sent_date=datetime.datetime.utcnow())


    @property
    def form(self):
        if self.request.method == 'POST':
            form = GiftForm(instance=self.gift, data=self.request.POST)
        else:
            form = GiftForm(instance=self.gift)
        if self.gift.id:
            form.fields['gift_type'].widget.choices = [(gift_type.id, gift_type) for gift_type in GiftType.objects.filter(community=self.community)]
        else:
            form.fields['gift_type'].widget.choices = [(gift_type.id, gift_type) for gift_type in GiftType.objects.filter(community=self.community, discontinued__isnull=True)]
        return form

    @login_required
    def add_view(request, member_id):
        view = GiftManager(request, member_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('member_profile', member_id=member_id)

        return render(request, 'savannahv2/gift_form.html', view.context)

    @login_required
    def edit_view(request, member_id, gift_id):
        view = GiftManager(request, member_id, gift_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('member_profile', member_id=member_id)

        return render(request, 'savannahv2/gift_form.html', view.context)


class TagEditForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name', 'color', 'keywords']
        widgets = {
            'color': forms.TextInput(attrs={'type': 'color'}),
        }
    def __init__(self, *args, **kwargs):
        super(TagEditForm, self).__init__(*args, **kwargs)
        if 'color' in self.initial:
            self.initial['color'] = '#%s'%self.initial['color']

    def clean_color(self):
        data = self.cleaned_data['color']
        return data.replace('#', '')
        
class MemberAdd(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "members"
        self.edit_member = Member(community_id=community_id, first_seen=datetime.datetime.utcnow(), last_seen=datetime.datetime.utcnow())
        self._edit_member_form = None
    @property
    def form(self):
        if self._edit_member_form is None:
            if self.request.method == 'POST':
                self._edit_member_form = MemberEditForm(instance=self.edit_member, data=self.request.POST)
            else:
                self._edit_member_form = MemberEditForm(instance=self.edit_member)
            self._edit_member_form.limit_to(self.community)
        return self._edit_member_form
        
    @login_required
    def as_view(request, community_id):
        view = MemberAdd(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            new_member = view.form.save()
            return redirect('member_profile', member_id=new_member.id)

        return render(request, "savannahv2/member_add.html", view.context)

class MemberTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['name', 'project', 'owner', 'due', 'detail']
        widgets = {
            'due': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }
    def __init__(self, *args, **kwargs):
        super(MemberTaskForm, self).__init__(*args, **kwargs)
        self.fields['due'].input_formats = ["%Y-%m-%dT%H:%M"]


class MemberTaskAdd(SavannahView):
    def __init__(self, request, member_id):
        self.member = get_object_or_404(Member, id=member_id)
        super(MemberTaskAdd, self).__init__(request, self.member.community.id)
        self.active_tab = "members"
        self._form = None

    @property
    def form(self):
        if self._form is None:
            task = Task(community=self.community, owner=self.request.user)
            if self.request.method == 'POST':
                self._form = MemberTaskForm(instance=task, data=self.request.POST)
            else:
                self._form = MemberTaskForm(instance=task)
            self._form.fields['owner'].widget.choices = [(user.id, user.username) for user in User.objects.filter(groups=self.community.managers).order_by('username')]
            self._form.fields['project'].widget.choices = [(project.id, project.name) for project in Project.objects.filter(community=self.community).order_by('-default_project', 'name')]
        return self._form

    @login_required
    def as_view(request, member_id):
        view = MemberTaskAdd(request, member_id)
        if request.method == "POST" and view.form.is_valid():
            task = view.form.save()
            task.stakeholders.add(view.member)
            return redirect('member_profile', member_id=member_id)

        return render(request, 'savannahv2/task_add.html', view.context)

class MemberTaskEdit(SavannahView):
    def __init__(self, request, member_id, task_id):
        self.member = get_object_or_404(Member, id=member_id)
        super(MemberTaskEdit, self).__init__(request, self.member.community.id)
        self.task = get_object_or_404(Task, id=task_id)
        self.active_tab = "members"
        self._form = None

    @property
    def form(self):
        if self._form is None:
            if self.request.method == 'POST':
                self._form = MemberTaskForm(instance=self.task, data=self.request.POST)
            else:
                self._form = MemberTaskForm(instance=self.task)
            self._form.fields['owner'].widget.choices = [(user.id, user.username) for user in User.objects.filter(groups=self.community.managers)]
            self._form.fields['project'].widget.choices = [(project.id, project.name) for project in Project.objects.filter(community=self.community).order_by('-default_project', 'name')]
        return self._form

    @login_required
    def as_view(request, member_id, task_id):
        view = MemberTaskEdit(request, member_id, task_id)
        if request.method == "POST" and view.form.is_valid():
            task = view.form.save()
            task.stakeholders.add(view.member)
            return redirect('member_profile', member_id=member_id)

        return render(request, 'savannahv2/task_edit.html', view.context)

    @login_required
    def mark_task_done(request, member_id):
        if request.method == "POST":
            task_id = request.POST.get('mark_done')
            try:
                task = Task.objects.get(id=task_id)
                task.done = datetime.datetime.utcnow()
                task.save()
            except:
                messages.error(request, "Task not found, could not mark as done.")
        return redirect('member_profile', member_id=member_id)