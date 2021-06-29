import operator
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max, Min

from notifications.models import Notification

from corm.models import *
from corm.connectors import ConnectionManager
from frontendv2.views import SavannahFilterView, SavannahView
from frontendv2.views.projects import TaskForm
from frontendv2.views.charts import FunnelChart

from frontendv2.views.tasks import AbstractTaskCalendarFeed

class ManagerTasksCalendar(AbstractTaskCalendarFeed):
    timezone = "UTC"
    file_name = "savannah-tasks.ics"

    def title(self, profile):
        return "%s Community Tasks" % profile.community.name

    def get_object(self, request, secret_key):
        return ManagerProfile.objects.get(secret_key=secret_key)

    def items(self, profile):
        return Task.objects.filter(
            community=profile.community, owner=profile.user, done__isnull=True
        ).order_by("-due")

class ManagerDashboard(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "dashboard"
        self.charts = set()

    @property
    def open_tasks(self):
        return Task.objects.filter(community=self.community, owner=self.request.user, done__isnull=True).order_by('due')

    @property
    def open_gifts(self):
        return Gift.objects.filter(community=self.community, received_date__isnull=True).order_by('sent_date')

    @property
    def member_watches(self):
        watches = MemberWatch.objects.filter(manager=self.request.user, member__community=self.community).order_by(IsNull('last_seen'), '-last_seen')
        watches = watches.select_related('member').prefetch_related('member__tags')
        return watches

    @property
    def new_members(self):
        members = Member.objects.filter(community=self.community).order_by("-first_seen")[:5]
        members = members.prefetch_related('tags')
        return members

    @property
    def new_contributors(self):
        members = Member.objects.filter(community=self.community)
        members = members.annotate(first_contrib=Min('contribution__timestamp')).filter(first_contrib__isnull=False)
        members = members.order_by('-first_contrib')[:5].prefetch_related('tags')
        actives = dict()
        for m in members:
            if m.first_contrib is not None:
                actives[m] = m.first_contrib
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:5]

    @property 
    def top_connections(self):
        if self.user_member:
            participants = Participant.objects.filter(initiator=self.user_member).exclude(member=self.user_member)
            participants = participants.values('member').annotate(connection_count=Count('conversation', distinct=True))
            for p in participants.order_by('-connection_count')[:10]:
                m = Member.objects.get(id=p['member'])
                m.connection_count = p['connection_count']
                yield m
        else:
            return []

    @property 
    def recent_connections(self):
        if self.user_member:
            connections = MemberConnection.objects.filter(from_member=self.user_member).order_by('-last_connected')[:10]
            connections = connections.select_related('to_member').prefetch_related('to_member__tags')
            return connections
        else:
            return []

    @property
    def recent_conversations(self):
        if self.user_member:
            recent = []
            channels = set()
            convos = Conversation.objects.filter(participation__member=self.user_member).order_by('-timestamp')
            convos = convos.select_related('channel').select_related('channel__source')
            for con in convos:
                if con.channel not in channels:
                    channels.add(con.channel)
                    recent.append((con.channel, con.timestamp, con.location))
                if len(recent) >= 10:
                    break
            return recent
        else:
            return []

    @login_required
    def mark_gift_received(request, community_id):
        if request.method == "POST":
            gift_id = request.POST.get('mark_received')
            try:
                gift = Gift.objects.get(id=gift_id, community_id=community_id)
                gift.received_date = datetime.datetime.utcnow()
                gift.save()
            except:
                messages.error(request, "Gift not found, could not mark as received.")
        return redirect('dashboard', community_id=community_id)

    @login_required
    def as_view(request, community_id):
        dashboard = ManagerDashboard(request, community_id)

        return render(request, 'savannahv2/manager_dashboard.html', dashboard.context)

class ManagerTaskEdit(SavannahView):
    def __init__(self, request, community_id, task_id):
        super(ManagerTaskEdit, self).__init__(request, community_id)
        self.task = get_object_or_404(Task, community=community_id, id=task_id)
        self.active_tab = "dashboard"

    @property
    def form(self):
        if self.request.method == 'POST':
            form = TaskForm(instance=self.task, data=self.request.POST)
        else:
            form = TaskForm(instance=self.task)
        form.fields['owner'].widget.choices = [(user.id, user.username) for user in User.objects.filter(groups=self.community.managers)]
        form.fields['project'].widget.choices = [(project.id, project.name) for project in Project.objects.filter(community=self.community).order_by('-default_project', 'name')]
        form.fields['stakeholders'].widget.choices = [(member.id, member.name) for member in Member.objects.filter(community=self.community)]
        return form

    @login_required
    def as_view(request, community_id, task_id):
        view = ManagerTaskEdit(request, community_id, task_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('dashboard', community_id=community_id)

        return render(request, 'savannahv2/manager_task_edit.html', view.context)

    @login_required
    def mark_task_done(request, community_id):
        if request.method == "POST":
            task_id = request.POST.get('mark_done')
            try:
                task = Task.objects.get(id=task_id, community_id=community_id)
                task.done = datetime.datetime.utcnow()
                task.save()
            except:
                messages.error(request, "Task not found, could not mark as done.")
        return redirect('dashboard', community_id=community_id)

class Overview(SavannahFilterView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "overview"
        self._membersChart = None
        self._channelsChart = None
        self._levelsChart = None
        self.charts = set()
        self.filter['custom_timespan'] = False
        self.filter['member'] = False
    
    @property 
    def member_count(self):
        members = self.community.member_set.all()
        return members.count()
        
    @property 
    def conversation_count(self):
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        return conversations.count()
        
    @property 
    def contribution_count(self):
        contributions = Contribution.objects.filter(community=self.community)
        return contributions.count()
        
    @property 
    def contributor_count(self):
        contributors = Member.objects.filter(community=self.community)
        return contributors.annotate(contrib_count=Count('contribution')).filter(contrib_count__gt=0).count()
        
    @property
    def most_active(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        members = members.filter(community=self.community).annotate(conversation_count=Count('speaker_in', filter=Q(speaker_in__timestamp__gte=self.rangestart, speaker_in__timestamp__lte=self.rangeend)))
        members = members.filter(conversation_count__gt=0)
        members = members.order_by('-conversation_count')

        return members[:10]

    @property
    def most_connected(self):
        members = Member.objects.filter(community=self.community)
        members = members.annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=self.rangestart, memberconnection__last_connected__lte=self.rangeend)))

        members = members.filter(connection_count__gt=0)
        members = members.order_by('-connection_count')
        return members[:10]

    def company_conversations(self):
        companies = Company.objects.filter(community=self.community, is_staff=False)
        convo_filter = Q(member__speaker_in__timestamp__lte=self.rangeend, member__speaker_in__timestamp__gte=self.rangestart)

        companies = companies.annotate(convo_count=Count('member__speaker_in', distinct=True, filter=convo_filter)).filter(convo_count__gt=0).order_by('-convo_count')
        return companies[:10]

    def company_contributions(self):
        companies = Company.objects.filter(community=self.community, is_staff=False)
        contrib_filter = Q(member__contribution__timestamp__lte=self.rangeend, member__contribution__timestamp__gte=self.rangestart)

        companies = companies.annotate(contrib_count=Count('member__contribution', filter=contrib_filter)).filter(contrib_count__gt=0).order_by('-contrib_count')

        return companies[:10]

    def getMembersChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()
            total = 0
            members = Member.objects.filter(community=self.community, first_seen__gte=self.rangestart, first_seen__lte=self.rangeend)
            total = Member.objects.filter(community=self.community, first_seen__lt=self.rangestart)

            total = total.count()
            counts['prev'] = total
            members = members.order_by("first_seen")
            for m in members:
                total += 1
                month = self.trunc_date(m.first_seen)

                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        return self.timespan_chart_keys(months)

    @property
    def members_chart_counts(self):
        (months, counts) = self.getMembersChart()
        cumulative_counts = []
        previous = counts['prev']
        for month in self.timespan_chart_keys(months):
            cumulative_counts.append(counts.get(month, previous))
            previous = cumulative_counts[-1]
        return cumulative_counts
        #return [counts.get(month, 0) for month in self.timespan_chart_keys(months)]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            counts = dict()
            total = 0
            conversations = Conversation.objects.filter(channel__source__community=self.community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))

            conversations = conversations.annotate(source_name=F('channel__source__name'), source_connector=F('channel__source__connector')).order_by("timestamp")
            for c in conversations:
                source_name = "%s (%s)" % (c.source_name, ConnectionManager.display_name(c.source_connector))
                if source_name not in counts:
                    counts[source_name] = 1
                else:
                    counts[source_name] += 1
            self._channelsChart = [(channel, count) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 8:
                other_count = sum([count for tag, count in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:7]
                self._channelsChart.append(("Other", other_count, "#efefef"))
        return self._channelsChart

    @property
    def channel_names(self):
        chart = self.getChannelsChart()
        return [channel[0] for channel in chart]

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart]

    @property
    def levels_chart(self):
        if self._levelsChart is None:
            project = get_object_or_404(Project, community=self.community, default_project=True)
            self._levelsChart = FunnelChart(project.id, project.name, stages=MemberLevel.LEVEL_CHOICES)
            for level, name in MemberLevel.LEVEL_CHOICES:
                levels = MemberLevel.objects.filter(community=self.community, project=project, level=level)
                levels = levels.filter(timestamp__gte=self.rangestart, timestamp__lte=self.rangeend)
                self._levelsChart.add(level, levels.count())
            self.charts.add(self._levelsChart)
        return self._levelsChart

    @login_required
    def as_view(request, community_id):
        dashboard = Overview(request, community_id)

        return render(request, 'savannahv2/overview.html', dashboard.context)
