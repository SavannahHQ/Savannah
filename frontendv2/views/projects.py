import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.contrib import messages
from django.http import JsonResponse
from django import forms

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, SavannahFilterView
from frontendv2.views.charts import FunnelChart

class Projects(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "projects"

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

class ProjectOverview(SavannahFilterView):
    def __init__(self, request, community_id, project_id):
        super().__init__(request, community_id)
        self.active_tab = "projects"
        self.project = get_object_or_404(Project, community=self.community, id=project_id)
        self._levelsChart = None

    def open_tasks(self):
        return Task.objects.filter(project=self.project, done__isnull=True)

    def core_levels(self):
        levels = MemberLevel.objects.filter(community=self.community, project=self.project, level=MemberLevel.CORE).order_by('-timestamp').select_related('member').prefetch_related('member__tags')
        levels = levels.filter(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            levels = levels.filter(member__tags=self.tag)
        if self.role:
            levels = levels.filter(member__role=self.role)
        return levels[:100]
        
    def contrib_levels(self):
        levels = MemberLevel.objects.filter(community=self.community, project=self.project, level=MemberLevel.CONTRIBUTOR).order_by('-timestamp').select_related('member').prefetch_related('member__tags')
        levels = levels.filter(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
        if self.tag:
            levels = levels.filter(member__tags=self.tag)
        if self.role:
            levels = levels.filter(member__role=self.role)
        return levels[:200]
        
    @property
    def levels_chart(self):
        if self._levelsChart is None:
            self._levelsChart = FunnelChart("project%s" % self.project.id, "Engagement Levels", stages=MemberLevel.LEVEL_CHOICES)
            for level, name in MemberLevel.LEVEL_CHOICES:
                levels = MemberLevel.objects.filter(community=self.community, project=self.project, level=level)
                levels = levels.filter(timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=self.timespan))
                if self.tag:
                    levels = levels.filter(member__tags=self.tag)
                if self.role:
                    levels = levels.filter(member__role=self.role)
                self._levelsChart.add(level, levels.count())
        self.charts.add(self._levelsChart)
        return self._levelsChart

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
        if view.project.default_project:
            messages.warning(request, "You can not add a default project")
            return redirect('projects', community_id=community_id)
        if request.method == "POST" and view.form.is_valid():
            project = view.form.save()
            messages.info(request, "Member level changes may take up to 24 hours to take effect.")
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
