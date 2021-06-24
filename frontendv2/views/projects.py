import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.db.models.functions import Trunc
from django.contrib import messages
from django.http import JsonResponse
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import FunnelChart
from frontendv2 import colors

class Projects(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "projects"

    def suggestion_count(self):
        return SuggestTask.objects.filter(community=self.community, status__isnull=True).count()

    def all_projects(self):
        return Project.objects.filter(community=self.community).annotate(contrib_count=Count('memberlevel__id', filter=Q(memberlevel__level__gte=MemberLevel.CONTRIBUTOR), distinct=True), task_count=Count('task', filter=Q(task__done__isnull=True), distinct=True)).order_by('-default_project', '-contrib_count')

    def all_charts(self):
        charts = []
        for project in Project.objects.filter(community=self.community):

            chart = FunnelChart(project.id, project.name, stages=MemberLevel.LEVEL_CHOICES)
            for level, name in MemberLevel.LEVEL_CHOICES:
                chart.add(level, MemberLevel.objects.filter(community=self.community, project=project, level=level).count())

            charts.append(chart)
        return charts

    @login_required
    def as_view(request, community_id):
        view = Projects(request, community_id)

        return render(request, "savannahv2/projects.html", view.context)

class ProjectsGraph(SavannahView):
    def __init__(self, request, community_id, json=False):
        self._is_json = json
        super().__init__(request, community_id)
        self.active_tab = "projects"

        self.level = MemberLevel.CONTRIBUTOR
        try:
            if 'level' in request.GET:
                if request.GET.get('level') == '':
                    request.session['level'] = None
                else:
                    self.level = int(request.GET.get('level'))
                    request.session['level'] = self.level
            elif 'level' in request.session:
                self.level = request.session.get('level')
        except:
            self.level = MemberLevel.CONTRIBUTOR
            request.session['level'] = MemberLevel.CONTRIBUTOR

    @login_required
    def as_view(request, community_id):
        view = ProjectsGraph(request, community_id)
        context = view.context
        context['level_name'] = MemberLevel.LEVEL_MAP[view.level]
        return render(request, "savannahv2/projects_graph.html", context)

    @login_required
    def as_json(request, community_id):
        view = ProjectsGraph(request, community_id, json=True)
        nodes = list()
        links = list()

        connected = set()
        projects = dict()
        from_date = datetime.datetime.now() - datetime.timedelta(days=366)

        levels = MemberLevel.objects.filter(project__community=view.community, project__default_project=False, level__gte=view.level)
        levels = levels.prefetch_related('member', 'project')
        levels.order_by('-timestamp')
        for level in levels[:1000]:

            if level.member_id not in connected:
                if level.member.role == Member.BOT:
                    tag_color = colors.MEMBER.BOT
                elif level.member.role == Member.STAFF:
                    tag_color = colors.MEMBER.STAFF
                else:
                    tag_color = colors.MEMBER.COMMUNITY
                link = reverse('member_profile', kwargs={'member_id':level.member_id})
                nodes.append({"id":'m%s'%level.member_id, "name":level.member.name, "link":link, "color":tag_color, "connections":0})
                connected.add(level.member_id)
            if level.project not in projects:
                projects[level.project] = 1
            else:
                projects[level.project] += 1
            links.append({"source":'prj%s'%level.project_id, "target":'m%s'%level.member_id})
            
        for project, count in projects.items():
            if project.tag:
                node_color = project.tag.color
            else:
                node_color = "8a8a8a"
            link = reverse('project_overview', kwargs={'community_id':view.community.id, 'project_id':project.id})
            nodes.append({"id":'prj%s'%project.id, "name":project.name, "link":link, "color":node_color, "connections":count})

                    
        return JsonResponse({"nodes":nodes, "links":links})

class ProjectOverview(SavannahView):
    def __init__(self, request, community_id, project_id):
        super().__init__(request, community_id)
        self.active_tab = "projects"
        self.project = get_object_or_404(Project, community=self.community, id=project_id)
        self._levelsChart = None
        self._engagementChart = None
        self.timespan = self.project.threshold_period

    def open_tasks(self):
        return Task.objects.filter(project=self.project, done__isnull=True)

    def core_levels(self):
        levels = MemberLevel.objects.filter(community=self.community, project=self.project, level=MemberLevel.CORE).order_by('-contribution_count', '-timestamp').select_related('member').prefetch_related('member__tags')
        levels = levels.filter(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        return levels[:100]
        
    def contrib_levels(self):
        levels = MemberLevel.objects.filter(community=self.community, project=self.project, level=MemberLevel.CONTRIBUTOR).order_by('-contribution_count', '-timestamp').select_related('member').prefetch_related('member__tags')
        levels = levels.filter(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        return levels[:200]
        
    @property
    def levels_chart(self):
        if self._levelsChart is None:
            self._levelsChart = FunnelChart("project%s" % self.project.id, "Engagement Levels", stages=MemberLevel.LEVEL_CHOICES)
            for level, name in MemberLevel.LEVEL_CHOICES:
                levels = MemberLevel.objects.filter(community=self.community, project=self.project, level=level)
                levels = levels.filter(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
                self._levelsChart.add(level, levels.count())
        self.charts.add(self._levelsChart)
        return self._levelsChart

    def getEngagementChart(self):
        if not self._engagementChart:
            conversations_counts = dict()
            activity_counts = dict()
            project_filter = Q(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
            if not self.project.default_project:
                project_filter = Q(channel__in=self.project.channels.all())
                if self.project.tag is not None:
                    project_filter = project_filter | Q(tags=self.project.tag)

            conversations = conversations = Conversation.objects.filter(channel__source__community=self.project.community)
            conversations = conversations.filter(project_filter)
            conversations = conversations.annotate(month=Trunc('timestamp', self.trunc_span)).values('month').annotate(convo_count=Count('id', distinct=True)).order_by('month')

            months = list()
            for c in conversations:
                month = self.trunc_date(c['month'])
                if month not in months:
                    months.append(month)
                conversations_counts[month] = c['convo_count']

            activity = Contribution.objects.filter(community=self.project.community)
            activity = activity.filter(project_filter)
            activity = activity.annotate(month=Trunc('timestamp', self.trunc_span)).values('month').annotate(contrib_count=Count('id', distinct=True)).order_by('month')

            for a in activity:
                month = self.trunc_date(a['month'])
                if month not in months:
                    months.append(month)
                activity_counts[month] = a['contrib_count']

            self._engagementChart = (sorted(months), conversations_counts, activity_counts)
        return self._engagementChart
        
    @property
    def engagement_chart_months(self):
        (months, conversations_counts, activity_counts) = self.getEngagementChart()
        return self.timespan_chart_keys(months)

    @property
    def engagement_chart_conversations(self):
        (months, conversations_counts, activity_counts) = self.getEngagementChart()
        return [conversations_counts.get(month, 0) for month in self.timespan_chart_keys(months)]

    @property
    def engagement_chart_activities(self):
        (months, conversations_counts, activity_counts) = self.getEngagementChart()
        return [activity_counts.get(month, 0) for month in self.timespan_chart_keys(months)]

    def trunc_date(self, date):
        if self.trunc_span == "month":
            return str(date)[:7]
        elif self.trunc_span == "day":
            return str(date)[:10]
        else:
            return "%s %s:00" % (str(date)[:10], date.hour)

    @property
    def trunc_span(self):
        if self.timespan > 120:
            return "month"
        elif self.timespan > 5:
            return "day"
        else:
            return "hour"

    @property
    def timespan_chart_span(self):
        if self.timespan > 120:
            return int(self.timespan / 30.4)
        elif self.timespan > 5:
            return self.timespan
        else:
            return self.timespan * 24

    def timespan_chart_keys(self, values):
        span_count = self.timespan_chart_span
        self.rangestart = datetime.datetime.utcnow() - datetime.timedelta(days=self.timespan)
        self.rangeend = datetime.datetime.utcnow()

        axis_values = []
        if self.trunc_span == "month":
            end = self.rangeend
            year = end.year
            month = end.month
            for i in range(span_count):
                axis_values.insert(0, "%04d-%02d" % (year, month))
                month -= 1
                if month < 1:
                    month = 12
                    year -= 1
            return axis_values
        elif self.trunc_span == "day":
            end = self.rangeend
            for i in range(span_count):
                day = self.trunc_date(end - datetime.timedelta(days=i))
                axis_values.insert(0, day)
            return axis_values
        elif self.trunc_span == "hour":
            end = self.rangeend
            for i in range(span_count):
                hour = self.trunc_date(end - datetime.timedelta(hours=i))
                axis_values.insert(0, hour)
            return axis_values
        else:
            return values[-span_count:]

    @login_required
    def as_view(request, community_id, project_id):
        view = ProjectOverview(request, community_id, project_id)

        return render(request, "savannahv2/project_overview.html", view.context)

    @login_required
    def mark_task_done(request, community_id, project_id):
        view = ProjectOverview(request, community_id, project_id)
        if request.method == "POST":
            task_id = request.POST.get('mark_done')
            try:
                task = Task.objects.get(id=task_id)
                task.done = datetime.datetime.utcnow()
                task.save()
            except:
                messages.error(request, "Task not found, could not mark as done.")
        return redirect('project_overview', community_id=community_id, project_id=project_id)

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'owner', 'tag', 'channels']

    def __init__(self, *args, **kwargs):
        super(ProjectForm, self).__init__(*args, **kwargs)

    def limit_to(self, community):
        self.fields['owner'].widget.choices = [(member.id, member.name) for member in Member.objects.filter(community=community)]
        self.fields['owner'].widget.choices.insert(0, ('', '-----'))
        self.fields['tag'].widget.choices = [(tag.id, tag.name) for tag in Tag.objects.filter(community=community)]
        self.fields['tag'].widget.choices.insert(0, ('', '-----'))
        self.fields['channels'].widget.choices = [(channel.id, "%s (%s)" % (channel.name, ConnectionManager.display_name(channel.source_connector))) for channel in Channel.objects.filter(source__community=community).annotate(source_connector=F('source__connector')).order_by('name')]

class ProjectAdd(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.project = Project(community=self.community)
        self.active_tab = "projects"

    @property
    def form(self):
        if self.request.method == 'POST':
            form = ProjectForm(instance=self.project, data=self.request.POST)
        else:
            form = ProjectForm(instance=self.project)
        form.limit_to(self.community)
        return form

    @login_required
    def as_view(request, community_id):
        view = ProjectAdd(request, community_id)
        if not view.community.management.can_add_project():
            view.community.management.upgrade_message(request, "You've reached your maximum allowed Projects")
            return redirect('projects', community_id=community_id)
        if view.project.default_project:
            messages.warning(request, "You can not add a default project")
            return redirect('projects', community_id=community_id)
        if request.method == "POST" and view.form.is_valid():
            project = view.form.save()
            messages.info(request, "Member level changes may take up to an hour to take effect.")
            return redirect('project_overview', community_id=community_id, project_id=project.id)

        return render(request, 'savannahv2/project_add.html', view.context)


class ProjectEdit(SavannahView):
    def __init__(self, request, community_id, project_id):
        super().__init__(request, community_id)
        self.project = get_object_or_404(Project, id=project_id)
        self.active_tab = "projects"

    @property
    def form(self):
        if self.request.method == 'POST':
            form = ProjectForm(instance=self.project, data=self.request.POST)
        else:
            form = ProjectForm(instance=self.project)
        form.limit_to(self.community)
        return form

    @login_required
    def as_view(request, community_id, project_id):
        view = ProjectEdit(request, community_id, project_id)
        if view.project.default_project:
            messages.warning(request, "You can not edit your community's default project")
            return redirect('project_overview', community_id=community_id, project_id=project_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('project_overview', community_id=community_id, project_id=project_id)

        return render(request, 'savannahv2/project_edit.html', view.context)


class ProjectThresholdsForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['threshold_period', 'threshold_user', 'threshold_participant', 'threshold_contributor', 'threshold_core']

    def __init__(self, *args, **kwargs):
        super(ProjectThresholdsForm, self).__init__(*args, **kwargs)

class ProjectThresholdEdit(SavannahView):
    def __init__(self, request, community_id, project_id):
        super().__init__(request, community_id)
        self.project = get_object_or_404(Project, id=project_id)
        self.active_tab = "projects"

    @property
    def form(self):
        if self.request.method == 'POST':
            form = ProjectThresholdsForm(instance=self.project, data=self.request.POST)
        else:
            form = ProjectThresholdsForm(instance=self.project)
        return form

    @login_required
    def as_view(request, community_id, project_id):
        view = ProjectThresholdEdit(request, community_id, project_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            messages.info(request, "Member level changes may take up to 24 hours to take effect.")
            return redirect('project_overview', community_id=community_id, project_id=project_id)

        return render(request, 'savannahv2/project_thresholds.html', view.context)

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['name', 'project', 'owner', 'due', 'detail', 'stakeholders']
        widgets = {
            'due': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }
    def __init__(self, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        self.fields['due'].input_formats = ["%Y-%m-%dT%H:%M"]


class ProjectTaskAdd(SavannahView):
    def __init__(self, request, community_id, project_id):
        super(ProjectTaskAdd, self).__init__(request, community_id)
        self.project = get_object_or_404(Project, id=project_id)
        self.active_tab = "projects"

    @property
    def form(self):
        task = Task(community=self.community, project=self.project, owner=self.request.user)
        if self.request.method == 'POST':
            form = TaskForm(instance=task, data=self.request.POST)
        else:
            form = TaskForm(instance=task)
        form.fields['owner'].widget.choices = [(user.id, user.username) for user in User.objects.filter(groups=self.community.managers).order_by('username')]
        form.fields['project'].widget.choices = [(project.id, project.name) for project in Project.objects.filter(community=self.community).order_by('-default_project', 'name')]
        form.fields['stakeholders'].widget.choices = [(member.id, member.name) for member in Member.objects.filter(community=self.community)]
        return form

    @login_required
    def as_view(request, community_id, project_id):
        view = ProjectTaskAdd(request, community_id, project_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('project_overview', community_id=community_id, project_id=project_id)

        return render(request, 'savannahv2/project_task_add.html', view.context)

class ProjectTaskEdit(SavannahView):
    def __init__(self, request, community_id, task_id):
        super(ProjectTaskEdit, self).__init__(request, community_id)
        self.task = get_object_or_404(Task, id=task_id)
        self.project = self.task.project
        self.active_tab = "projects"

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
    def as_view(request, community_id, project_id, task_id):
        view = ProjectTaskEdit(request, community_id, task_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('project_overview', community_id=community_id, project_id=project_id)

        return render(request, 'savannahv2/project_task_edit.html', view.context)
