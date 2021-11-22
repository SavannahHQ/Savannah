import operator
import datetime
import json
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max
from django.contrib.auth import authenticate, login as login_user, logout as logout_user
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UsernameField, SetPasswordForm
from django.contrib import messages
from django.conf import settings
from django import forms

from corm.models import *
from frontendv2 import colors
from frontendv2.models import EmailMessage, PasswordResetRequest, PublicDashboard

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

class NewUserForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email")
        field_classes = {'username': UsernameField}

    def __init__(self, *args, **kwargs):
        super(UserCreationForm, self).__init__(*args, **kwargs)
        self.fields['email'].required = True

def login(request):
    next_view = 'home'
    if 'next' in request.GET:
        next_view = request.GET.get('next', 'home')

    if request.user.is_authenticated:
        return redirect(next_view)

    context = {
        "signup_form":  NewUserForm(),
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
                return redirect(next_view)
            else:
                context["login_form"] = login_form
                context["action"] = "login"
        elif request.POST.get("action") == "signup":
            signup_form = NewUserForm(data=request.POST)
            if signup_form.is_valid():
                signup_form.save()
                username = signup_form.cleaned_data.get("username")
                raw_password = signup_form.cleaned_data.get("password1")
                user = authenticate(username=username, password=raw_password)
                login_user(request, user, backend=user.backend)
                return redirect(next_view)
            else:
                context["signup_form"] = signup_form
                context["action"] = "signup"

    return render(request, 'savannahv2/login.html', context)

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'})
    )

def password_reset_request(request):
    context = {}
    if request.method == "POST":
        form = PasswordResetRequestForm(data=request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            PasswordResetRequest.send(email)
            messages.success(request, "Password reset email sent")
            return redirect("login")
        else:
            messages.error(request, "Invalid emails")

    else:
        form = PasswordResetRequestForm()

    context['form'] = form
    return render(request, 'savannahv2/password_reset.html', context)


def reset_password(request, request_key):
    try:
        reset = PasswordResetRequest.objects.get(key=request_key)
        if reset.expires >= datetime.datetime.utcnow():
            if request.method == "POST":
                form = SetPasswordForm(user=reset.user, data=request.POST)
                if form.is_valid():
                    user = form.save()
                    login_user(request, user)
                    messages.success(request, "Your password has been reset")
                    reset.delete()
                    return redirect('home')
            else:
                form = SetPasswordForm(user=reset.user)

            context = {
                'form': form
            }
            return render(request, 'savannahv2/password_reset.html', context)
        else:
            messages.error(request, "Your password reset request has expired")
    except:
        messages.error(request, "Invalid reset request")
    return redirect('login')

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

def get_session_community(request):
    community_id = request.session.get('community')
    if community_id is not None:
        try:
            return Community.objects.get(id=community_id)
        except:
            pass
    return None

class SavannahView:
    def __init__(self, request, community_id):
        request.session['community'] = community_id
        self.request = request
        if request.user.is_superuser:
            self.community = get_object_or_404(Community, id=community_id)
        elif request.user.is_authenticated:
            self.community = get_object_or_404(Community, Q(owner=self.request.user) | Q(managers__in=self.request.user.groups.all()), id=community_id)
        else:
            self.community = None
        if request.user.is_authenticated:
            self.manager_profile, created = ManagerProfile.objects.update_or_create(user=request.user, community=self.community, defaults={'last_seen': datetime.datetime.utcnow()})
            self.user_member = self.manager_profile.member
        else:
            self.manager_profile = None
            self.user_member = None
        self.active_tab = ""
        self.charts = set()

        self._add_sources_message()


    def _add_sources_message(self):
        if self.request.method == "GET" and self.request.user.is_authenticated:
            if self.community.status == Community.SUSPENDED:
                messages.warning(self.request, "Updates to this community have been suspended due to a billing problem. Please update your <a href=\"%s\">billing information</a> to resume updates." % reverse('billing:manage_account', kwargs={'community_id':self.community.id}))
            elif self.community.status == Community.DEACTIVE:
                messages.error(self.request, "This community has been deactivated and will not recieve updates. You may reactive is by <a href=\"%s\">starting a new subscription</a>." % (reverse('billing:signup_subscribe', kwargs={'community_id':self.community.id}),))
            elif self.community.status == Community.ARCHIVED:
                messages.info(self.request, "This community has been archived and will no longer receive updates.")
            elif self.community.source_set.all().count() == 0:
                messages.info(self.request, "It looks like you haven't added any data sources to <b>%s</b> yet, you can do that on the <a class=\"btn btn-primary btn-sm\" href=\"%s\"><i class=\"fas fa-file-import\"></i> Sources</a> page." % (self.community.name, reverse('sources', kwargs={'community_id':self.community.id})))
            elif self.community.status == Community.SETUP:
                messages.success(self.request, "Your community is all set! <a href=\"%s\">Start you subsription now</a> and Savannah will begin importing your data." % reverse('billing:signup_org', kwargs={'community_id':self.community.id}))
        
    @property
    def context(self):
        if self.request.user.is_authenticated:
            communities = Community.objects.filter(Q(status__lte=Community.SUSPENDED)|Q(status=Community.DEMO)).filter(Q(owner=self.request.user) | Q(managers__in=self.request.user.groups.all())).annotate(member_count=Count('member')).order_by('-member_count')
        else:
            communities = []
        return {
            "SITE_ROOT": settings.SITE_ROOT,
            "communities": communities,
            "active_community": self.community,
            "active_tab": self.active_tab,
            "view": self,
        }

class SavannahFilterView(SavannahView):
    def __init__(self, request, community_id):
        self.MAX_TIMESPAN = 365
        if community_id != request.session.get("community") or ('clear' in request.GET and request.GET.get('clear') == 'all'):
            request.session['timefilter'] = 'timespan'
            request.session['timespan'] = self.MAX_TIMESPAN
            request.session['tag'] = None
            request.session['member_tag'] = None
            request.session['member_company'] = None
            request.session['role'] = None
            request.session['type'] = None
            request.session['source'] = None
        super().__init__(request, community_id)
        self.filter = {
            'timespan': True,
            'custom_timespan': True,
            'member': True,
            'member_role': True,
            'member_tag': True,
            'member_company': True,
            'tag': False,
            'source': False,
            'contrib_type': False,
            'source': False,
        }

        self.tag = None
        try:
            if 'tag' in request.GET:
                if request.GET.get('tag') == '':
                    request.session['tag'] = None
                else:
                    self.tag = Tag.objects.get(community=self.community, name=request.GET.get('tag'))
                    request.session['tag'] = request.GET.get('tag')
            elif 'tag' in request.session:
                self.tag = Tag.objects.get(community=self.community, name=request.session.get('tag'))
        except:
            self.tag = None
            request.session['tag'] = None

        self.member_tag = None
        try:
            if 'member_tag' in request.GET:
                if request.GET.get('member_tag') == '':
                    request.session['member_tag'] = None
                else:
                    self.member_tag = Tag.objects.get(community=self.community, name=request.GET.get('member_tag'))
                    request.session['member_tag'] = request.GET.get('member_tag')
            elif 'member_tag' in request.session:
                self.member_tag = Tag.objects.get(community=self.community, name=request.session.get('member_tag'))
        except:
            self.member_tag = None
            request.session['member_tag'] = None

        self.member_company = None
        try:
            if 'member_company' in request.GET:
                if request.GET.get('member_company') == '':
                    request.session['member_company'] = None
                else:
                    self.member_company = Company.objects.get(community=self.community, id=request.GET.get('member_company'))
                    request.session['member_company'] = request.GET.get('member_company')
            elif 'member_company' in request.session:
                self.member_company = Company.objects.get(community=self.community, id=request.session.get('member_company'))
        except:
            self.member_company = None
            request.session['member_company'] = None

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

        self.contrib_type = None
        try:
            if 'type' in request.GET:
                if request.GET.get('type') == '':
                    request.session['type'] = None
                else:
                    self.contrib_type = request.GET.get('type')
                    request.session['type'] = request.GET.get('type')
            elif 'type' in request.session:
                self.contrib_type = request.session.get('type')
        except:
            self.contrib_type = None
            request.session['type'] = None

        self.source = None
        self.exclude_source = False
        try:
            if 'source' in request.GET:
                if request.GET.get('source') == '':
                    request.session['source'] = None
                else:
                    source_id = int(request.GET.get('source'))
                    if source_id < 0:
                        self.exclude_source = True
                        source_id = abs(source_id)
                    self.source = Source.objects.get(community=self.community, id=source_id)
                    request.session['source'] = request.GET.get('source')
            elif 'source' in request.session and request.session.get('source') is not None:
                source_id = int(request.session.get('source'))
                if source_id < 0:
                    self.exclude_source = True
                    source_id = abs(source_id)
                self.source = Source.objects.get(community=self.community, id=source_id)
        except Exception as e:
            print(e)
            self.source = None
            self.exclude_source = False
            request.session['source'] = None

        self.rangestart = None
        self.rangeend = None
        self.timespan = self.MAX_TIMESPAN
        self.DATE_FORMAT = '%Y-%m-%d'
        if 'timefilter' not in request.session:
            request.session['timefilter'] = 'timespan'
        try:
            if 'rangestart' in request.GET:
                if request.GET.get('rangestart') == '':
                    request.session['rangestart'] = None
                else:
                    self.rangestart = datetime.datetime.strptime(request.GET.get('rangestart'), self.DATE_FORMAT)
                    request.session['rangestart'] = self.rangestart.strftime(self.DATE_FORMAT)
                    request.session['timefilter'] = 'range'
            elif 'rangestart' in request.session:
                self.rangestart = datetime.datetime.strptime(request.session.get('rangestart'), self.DATE_FORMAT)

            if 'rangeend' in request.GET:
                if request.GET.get('rangeend') == '':
                    request.session['rangeend'] = None
                else:
                    self.rangeend = datetime.datetime.strptime(request.GET.get('rangeend'), self.DATE_FORMAT)
                    self.rangeend = self.rangeend.replace(hour=23, minute=59, second=59)
                    request.session['rangeend'] = self.rangeend.strftime(self.DATE_FORMAT)
                    request.session['timefilter'] = 'range'
            elif 'rangeend' in request.session:
                self.rangeend = datetime.datetime.strptime(request.session.get('rangeend'), self.DATE_FORMAT)

            if 'timespan' in request.GET:
                if request.GET.get('timespan') == '':
                    request.session['timespan'] = self.MAX_TIMESPAN
                else:
                    self.timespan = int(request.GET.get('timespan'))
                    if self.timespan > self.MAX_TIMESPAN or self.timespan < 1:
                        self.timespan = self.MAX_TIMESPAN
                    request.session['timespan'] = self.timespan
                request.session['timefilter'] = 'timespan'
            elif 'timespan' in request.session:
                self.timespan = request.session.get('timespan')

        except Exception as e:
            self.timespan = self.MAX_TIMESPAN
            request.session['timespan'] = self.MAX_TIMESPAN
            request.session['timefilter'] = 'timespan'

        self.timefilter = request.session['timefilter']
        if self.timefilter == 'timespan':
            self.rangestart = datetime.datetime.utcnow() - datetime.timedelta(days=self.timespan)
            self.rangeend = datetime.datetime.utcnow()
        else:
            self.timespan = (self.rangeend - self.rangestart).days

    def filters_as_dict(self, request):
        filters = dict()
        for name, used in self.filter.items():
            session_name = name
            if name == 'member_role':
                session_name = 'role'
            if name == 'contrib_type':
                session_name = 'type'
            if used:
                filters[name] = request.session.get(session_name, None)
        filters['rangestart'] = request.session.get('rangestart', None)
        filters['rangeend'] = request.session.get('rangeend', None)
        filters['timefilter'] = request.session.get('timefilter', 'timespan')
        return filters

    @property
    def is_filtered(self):
        if self.filter['timespan'] and (self.timespan != self.MAX_TIMESPAN or self.rangeend.date != datetime.datetime.utcnow().date):
            return True
        if self.filter['member_role'] and self.role is not None:
            return True
        if self.filter['member_tag'] and self.member_tag is not None:
            return True
        if self.filter['member_company'] and self.member_company is not None:
            return True
        if self.filter['tag'] and self.tag is not None:
            return True
        if self.filter['source'] and self.source is not None:
            return True
        if self.filter['contrib_type'] and self.contrib_type is not None:
            return True

    @property
    def timespan_display(self):
        if self.timespan == 365:
            return "Past Year"
        elif self.timespan == 183:
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
        if self.timespan == 1:
            return "fas fa-calendar-day"
        elif self.timespan <= 7:
            return "fas fa-calendar-week"
        elif self.timespan <= 90:
            return "fas fa-calendar-alt"
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
        if self.timespan > 92:
            return "month"
        elif self.timespan > 5:
            return "day"
        else:
            return "hour"

    @property
    def timespan_chart_span(self):
        if self.timespan > 92:
            return int(self.timespan / 30.4)
        elif self.timespan > 5:
            return self.timespan
        else:
            return self.timespan * 24

    def timespan_chart_keys(self, values):
        span_count = self.timespan_chart_span

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

    def publish_view(self, request, page, view_name, show_members=False, show_companies=False, pin_time=None):
        filters = self.filters_as_dict(request)
        default_name = ""
        if page in PublicDashboard.PAGES:
            default_name = PublicDashboard.PAGES.get(page)
        if filters.get('tag', None):
            default_name = self.tag.name.title() + " " + default_name
        if filters.get('member_role', None):
            if filters.get('member_role') == 'bot':
                default_name = default_name + " (excluding bots)"
            else:
                default_name = filters.get('member_role').title() +" "+ default_name
        if filters.get('member_tag', None):
            if filters.get('member_role', None) or filters.get('member_company', None):
                default_name = self.member_tag.name.title() + " " + default_name
            else:
                default_name = default_name + " by " + self.member_tag.name.title()

        if filters.get('member_company', None):
            default_name = self.member_company.name + " " + default_name

        if filters.get('timefilter', 'timespan') == 'timespan' and filters.get('timespan', self.MAX_TIMESPAN) < self.MAX_TIMESPAN:
            default_name = self.timespan_display + " " + default_name
        if filters.get('source', None):
            if int(filters.get('source', 0)) < 1:
                default_name = default_name + " not in %s %s" % (self.source.name, self.source.connector_name)
            else:
                default_name = default_name + " in %s %s" % (self.source.name, self.source.connector_name)

        if filters.get('timefilter', 'timespan') == 'range' and not pin_time:
            pin_time = True
        else:
            pin_time = False

        dashboard = PublicDashboard(
            community=self.community,
            page=page, 
            created_by=request.user, 
            display_name=default_name, 
            show_members=show_members,
            show_companies=show_companies,
            pin_time=pin_time,
            filters=filters
        )
        if request.method == "POST":
            form = PublicViewForm(instance=dashboard, data=request.POST)
            if form.is_valid():
                new_pub = form.save()
                messages.success(request, "Your shared dashboard is ready! You can share <a href=\"%s\">this link</a> publicly for anyone to view it." % new_pub.get_absolute_url())
                return redirect(view_name, dashboard_id=new_pub.id)
            else:
                messages.error(request, "Unable to create dashboard.")

        else:
            form = PublicViewForm(instance=dashboard)

        context = dashboard.apply(self)
        context.update({
            'form': form,
            'filters': filters,
        })
        return render(request, 'savannahv2/publish_dashboard.html', context)
        
class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = [
            'name', 
            'logo', 
            'suggest_tag',
            'suggest_company',
            'suggest_merge',
            'suggest_contribution',
            'suggest_task',
        ]
    
class CommunityCreationEmail(EmailMessage):
    def __init__(self, community):
        super(CommunityCreationEmail, self).__init__(community.owner, community)
        self.subject = "A new community had been created: %s" % self.community.name
        self.category = "community_creation"

        self.text_body = "emails/new_community_created.txt"
        self.html_body = "emails/new_community_created.html"

def new_community(request):
    if settings.IS_DEMO:
        return redirect('demo:new')
    else:
        return redirect('billing:signup')
    
def branding(request):
    context = {
        "colors": colors
    }
    return render(request, 'savannahv2/branding.html', context)

# @login_required
# def new_community(request):
#     community = Community(owner=request.user)
#     if request.method == "POST":
#         form = CommunityForm(request.POST, files=request.FILES, instance=community)
#         if form.is_valid():
#             new_community = form.save()
#             new_community.bootstrap()
#             msg = CommunityCreationEmail(new_community)
#             msg.send(settings.ADMINS)
#             messages.success(request, "Welcome to your new Communtiy! Learn what to do next in our <a target=\"_blank\" href=\"http://docs.savannahhq.com/getting-started/\">Getting Started</a> guide.")
#             return redirect('dashboard', community_id=new_community.id)
#     else:
#         form = CommunityForm(instance=community)

#     communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all())).annotate(member_count=Count('member')).order_by('-member_count')
#     context = {
#         "communities": communities,
#         "form": form,
#     }
#     return render(request, 'savannahv2/community_add.html', context)

class PublicViewForm(forms.ModelForm):
    class Meta:
        model = PublicDashboard
        fields = [
            'display_name', 
            'show_members', 
            'show_companies', 
            'pin_time',
        ]
