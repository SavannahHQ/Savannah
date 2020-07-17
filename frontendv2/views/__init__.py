import operator
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max
from django.contrib.auth import authenticate, login as login_user, logout as logout_user
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import PasswordResetView as DjangoPasswordResetView
from django.contrib import messages
from django import forms

from corm.models import *

# Create your views here.
def index(request):
    if not settings.ALPHA:
        return redirect('home')

    sayings = [
        "Herd your cats",
        "Build a better community",
        "Manage your community relationships"
    ]
    return render(request, 'savannahv2/index.html', {'sayings': sayings})

def logout(request):
    if request.user.is_authenticated:
        logout_user(request)
    return redirect(reverse("login") + "?next=%s" % request.GET.get('next'))

def login(request):
    if request.user.is_authenticated:
        return redirect('home')

    context = {
        "signup_form":  UserCreationForm(),
        "login_form": AuthenticationForm(),
    }
    if request.method == "POST":
        if request.POST.get("action") == "login":
            login_form = AuthenticationForm(data=request.POST)
            if login_form.is_valid():
                username = login_form.cleaned_data.get("username")
                raw_password = login_form.cleaned_data.get("password")
                user = authenticate(username=username, password=raw_password)
                login_user(request, user, backend=user.backend)
                return redirect('home')
            else:
                context["login_form"] = login_form
                context["action"] = "login"
        elif request.POST.get("action") == "signup":
            signup_form = UserCreationForm(data=request.POST)
            if signup_form.is_valid():
                signup_form.save()
                username = signup_form.cleaned_data.get("username")
                raw_password = signup_form.cleaned_data.get("password1")
                user = authenticate(username=username, password=raw_password)
                login_user(request, user, backend=user.backend)
                return redirect('home')
            else:
                context["signup_form"] = signup_form
                context["action"] = "signup"

    return render(request, 'savannahv2/login.html', context)

@login_required
def home(request):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all())).annotate(member_count=Count('member')).order_by('-member_count')
    count = communities.count()
    if count < 1 and not settings.BETA:
        return redirect('add-community')
    elif count == 1:
        return redirect('dashboard', community_id=communities[0].id)

    context = {
        "communities": communities,
        "BETA": settings.BETA,
        "OPEN_BETA": settings.OPEN_BETA
    }
    return render(request, 'savannahv2/home.html', context)

class SavannahView:
    def __init__(self, request, community_id):
        request.session['community'] = community_id
        self.request = request
        self.community = get_object_or_404(Community, Q(owner=self.request.user) | Q(managers__in=self.request.user.groups.all()), id=community_id)
        self.active_tab = ""

        try:
            self.user_member = Member.objects.get(user=self.request.user, community=self.community)
        except:
            self.user_member = None

        self._add_sources_message()

    def _add_sources_message(self):
        if self.request.method == "GET" and self.community.source_set.all().count() == 0:
            messages.info(self.request, "It looks like you haven't added any data sources to <b>%s</b> yet, you can do that on the <a class=\"btn btn-primary btn-sm\" href=\"%s\"><i class=\"fas fa-file-import\"></i> Sources</a> page." % (self.community.name, reverse('sources', kwargs={'community_id':self.community.id})))

    @property
    def context(self):
        communities = Community.objects.filter(Q(owner=self.request.user) | Q(managers__in=self.request.user.groups.all())).annotate(member_count=Count('member')).order_by('-member_count')
        return {
            "communities": communities,
            "active_community": self.community,
            "active_tab": self.active_tab,
            "view": self,
        }

class SavannahFilterView(SavannahView):
    def __init__(self, request, community_id):
        self.MAX_TIMESPAN = 365
        if community_id != request.session.get("community"):
            request.session['tag'] = None
            request.session['role'] = None
            request.session['timespan'] = self.MAX_TIMESPAN
        super().__init__(request, community_id)

        self.tag = None
        try:
            if 'tag' in request.GET:
                if request.GET.get('tag') == '':
                    equest.session['tag'] = None
                else:
                    self.tag = Tag.objects.get(community=self.community, name=request.GET.get('tag'))
                    request.session['tag'] = request.GET.get('tag')
            elif 'tag' in request.session:
                self.tag = Tag.objects.get(community=self.community, name=request.session.get('tag'))
        except:
            self.tag = None
            request.session['tag'] = None

        self.role = None
        try:
            if 'role' in request.GET:
                if request.GET.get('role') == '':
                    request.session['role'] = None
                else:
                    self.role = request.GET.get('role')
                    request.session['role'] = request.GET.get('role')
            elif 'role' in request.session:
                self.role = request.session.get('role')
        except:
            self.role = None
            request.session['role'] = None

        self.timespan = self.MAX_TIMESPAN
        try:
            if 'timespan' in request.GET:
                if request.GET.get('timespan') == '':
                    request.session['timespan'] = self.MAX_TIMESPAN
                else:
                    self.timespan = int(request.GET.get('timespan'))
                    if self.timespan > self.MAX_TIMESPAN or self.timespan < 1:
                        self.timespan = self.MAX_TIMESPAN
                    request.session['timespan'] = self.timespan
            elif 'timespan' in request.session:
                self.timespan = request.session.get('timespan')
        except:
            self.timespan = self.MAX_TIMESPAN
            request.session['timespan'] = self.MAX_TIMESPAN

    @property
    def timespan_display(self):
        if self.timespan == 180:
            return "6 Months"
        elif self.timespan == 30:
            return "30 Days"
        elif self.timespan == 7:
            return "Last Week"
        elif self.timespan == 1:
            return "Today"
        else:
            return "%s Days" % self.timespan

    @property
    def timespan_icon(self):
        if self.timespan == 180:
            return "fas fa-calendar"
        elif self.timespan == 30:
            return "fas fa-calendar-alt"
        elif self.timespan == 7:
            return "fas fa-calendar-week"
        elif self.timespan == 1:
            return "fas fa-calendar-day"
        else:
            return "fas fa-calendar"

    def trunc_date(self, date):
        if self.trunc_span == "month":
            return str(date)[:7]
        elif self.trunc_span == "day":
            return str(date)[:10]
        else:
            return "%s %s:00" % (str(date)[:10], date.hour)

    @property
    def trunc_span(self):
        if self.timespan > 30:
            return "month"
        elif self.timespan > 3:
            return "day"
        else:
            return "hour"

    @property
    def timespan_chart_span(self):
        if self.timespan > 180:
            return 12
        elif self.timespan > 30:
            return 6
        elif self.timespan > 3:
            return self.timespan
        else:
            return self.timespan * 24

    def timespan_chart_keys(self, values):
        span_count = self.timespan_chart_span
        axis_values = []
        if self.trunc_span == "month":
            end = datetime.datetime.utcnow()
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
            end = datetime.datetime.utcnow()
            for i in range(span_count):
                day = self.trunc_date(end - datetime.timedelta(days=i))
                axis_values.insert(0, day)
            return axis_values
        elif self.trunc_span == "hour":
            end = datetime.datetime.utcnow()
            for i in range(span_count):
                hour = self.trunc_date(end - datetime.timedelta(hours=i))
                axis_values.insert(0, hour)
            return axis_values
        else:
            return values[-span_count:]

class NewCommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ['name', 'logo']
    
@login_required
def new_community(request):
    community = Community(owner=request.user)
    if request.method == "POST":
        form = NewCommunityForm(request.POST, files=request.FILES, instance=community)
        if form.is_valid():
            new_community = form.save()
            new_community.bootstrap()
            messages.success(request, "Welcome to your new Communtiy!")
            return redirect('dashboard', community_id=new_community.id)
    else:
        form = NewCommunityForm(instance=community)

    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all())).annotate(member_count=Count('member')).order_by('-member_count')
    context = {
        "communities": communities,
        "form": form,
    }
    return render(request, 'savannahv2/community_add.html', context)
