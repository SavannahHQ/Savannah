import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.contrib import messages
from django.http import JsonResponse
from django import forms
from django.contrib.auth import authenticate, login as login_user, logout as logout_user
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import PasswordResetView as DjangoPasswordResetView

from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView
from frontendv2.models import ManagerInvite

class Managers(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "community"

    def all_managers(self):
        if self.community.managers is not None:
            return self.community.managers.user_set.all()
        else:
            return []

    def invitations(self):
        return ManagerInvite.objects.filter(community=self.community)

    @login_required
    def as_view(request, community_id):
        view = Managers(request, community_id)
        if request.method == "POST":
            pass
        return render(request, "savannahv2/managers.html", view.context)

class ManagerInviteForm(forms.Form):
    emails = forms.CharField(label="Email Addresses", help_text="Comma-separated list of email addresses")


class InviteManager(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "community"

    @login_required
    def as_view(request, community_id):
        view = InviteManager(request, community_id)
        if request.method == "POST":
            view.form = ManagerInviteForm(data=request.POST)
            if view.form.is_valid():
                emails = [addr.strip() for addr in view.form.cleaned_data['emails'].split(',')]
                for email in emails:
                    ManagerInvite.send(view.community, request.user, email)
                messages.success(request, "Invitations sent!")
                return redirect("managers", community_id=community_id)
            else:
                messages.error(request, "Invalid emails")

        else:
            view.form = ManagerInviteForm()
        return render(request, "savannahv2/manager_invite.html", view.context)

class AcceptManager(SavannahView):
    def __init__(self, request, community_id):
        self.request = request
        self.community = get_object_or_404(Community, id=community_id)
        self.active_tab = "community"

    def as_view(request, community_id):
        view = AcceptManager(request, community_id)
        context = {
            "view": view,
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
                else:
                    context["signup_form"] = signup_form
                    context["action"] = "signup"

        if request.user.is_authenticated:
            confirmation_key = request.GET.get('confirmation', None)
            try:
                invite = ManagerInvite.objects.get(community=view.community, key=confirmation_key)
                if invite.expires >= datetime.datetime.utcnow():
                    view.community.managers.user_set.add(request.user)
                    messages.success(request, "You've been added to %s as a new Manager!" % view.community.name)
                    invite.delete()
                    return redirect('dashboard', community_id=community_id)
                else:
                    context['error'] = "Your invitation has expired"
            except:
                context['error'] = "Invalid invitation"

        return render(request, "savannahv2/manager_accept.html", context)
