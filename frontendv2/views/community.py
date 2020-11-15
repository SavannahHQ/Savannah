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
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm
from django.contrib.auth.views import PasswordResetView as DjangoPasswordResetView


from corm.models import *
from corm.connectors import ConnectionManager

from frontendv2.views import SavannahView, CommunityForm
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
                    if not request.user.email:
                        request.user.email = invite.email
                        request.user.save()
                    messages.success(request, "You've been added to %s as a new Manager!" % view.community.name)
                    invite.delete()
                    return redirect('dashboard', community_id=community_id)
                else:
                    context['error'] = "Your invitation has expired"
            except:
                context['error'] = "Invalid invitation"

        return render(request, "savannahv2/manager_accept.html", context)


def resend_invitation(request, community_id):
    if request.method == "POST":
        community = get_object_or_404(Community, id=community_id)
        invite_id = request.POST.get('invite_id', 0)
        try:
            invite = ManagerInvite.objects.get(id=invite_id)
        except ManagerInvite.DoesNotExist:
            messages.error(request, "Invitation not found")
            return redirect('managers', commuinity_id=community_id)
        ManagerInvite.send(community, request.user, invite.email)
        messages.success(request, "Invitation has been resent")
    return redirect('managers', community_id=community_id)

def revoke_invitation(request, community_id):
    if request.method == "POST":
        community = get_object_or_404(Community, id=community_id)
        invite_id = request.POST.get('invite_id', 0)
        try:
            invite = ManagerInvite.objects.get(id=invite_id)
        except ManagerInvite.DoesNotExist:
            messages.error(request, "Invitation not found")
            return redirect('managers', commuinity_id=community_id)
        invite.delete()
        messages.success(request, "Invitation has been revoked")
    return redirect('managers', community_id=community_id)

class Gifts(SavannahView):
    def __init__(self, request, community_id):
        super().__init__(request, community_id)
        self.active_tab = "gifts"

    def available_gift_types(self):
        return GiftType.objects.filter(community=self.community, discontinued__isnull=True).annotate(sent=Count('gift'))

    def discontinued_gift_types(self):
        return GiftType.objects.filter(community=self.community, discontinued__isnull=False).annotate(sent=Count('gift'))

    @login_required
    def as_view(request, community_id):
        view = Gifts(request, community_id)
        if request.method == "POST":
            pass
        return render(request, "savannahv2/gifts.html", view.context)

class GiftTypeForm(forms.ModelForm):
    class Meta:
        model = GiftType
        fields = ["name", "contents", "discontinued"]
        widgets = {
            'discontinued': forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={'type': 'datetime-local'}),
        }
    def __init__(self, *args, **kwargs):
        super(GiftTypeForm, self).__init__(*args, **kwargs)
        self.fields['discontinued'].input_formats = ["%Y-%m-%dT%H:%M"]


class GiftTypeManager(SavannahView):
    def __init__(self, request, community_id, type_id=None):
        super(GiftTypeManager, self).__init__(request, community_id)
        self.active_tab = "gifts"
        if type_id:
            self.gift = get_object_or_404(GiftType, id=type_id)
        else:
            self.gift = GiftType(community=self.community)

    @property
    def form(self):
        if self.request.method == 'POST':
            form = GiftTypeForm(instance=self.gift, data=self.request.POST)
        else:
            form = GiftTypeForm(instance=self.gift)
        return form

    @property
    def sent_gifts(self):
        return Gift.objects.filter(community=self.community, gift_type=self.gift).order_by('-sent_date')

    @login_required
    def add_view(request, community_id):
        view = GiftTypeManager(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('gifts', community_id=community_id)

        return render(request, 'savannahv2/gift_type_form.html', view.context)


    @login_required
    def edit_view(request, community_id, type_id):
        view = GiftTypeManager(request, community_id, type_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            return redirect('gifts', community_id=community_id)

        return render(request, 'savannahv2/gift_type_form.html', view.context)

class ManagerPreferencesForm(forms.ModelForm):
    class Meta:
        model = ManagerProfile
        fields = ["realname", "contact_email", "tz", "send_notifications"]


class ManagerPreferences(SavannahView):
    def __init__(self, request, community_id):
        super(ManagerPreferences, self).__init__(request, community_id)
        self.community = get_object_or_404(Community, id=community_id)
        self.manager = get_object_or_404(ManagerProfile, community=self.community, user=request.user)
        self.active_tab = "community"

    @property
    def form(self):
        if self.request.method == 'POST':
            form = ManagerPreferencesForm(instance=self.manager, data=self.request.POST)
        else:
            form = ManagerPreferencesForm(instance=self.manager)
        return form

    @login_required
    def as_view(request, community_id):
        view = ManagerPreferences(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            view.form.save()
            messages.success(request, "Your preferences have been updated")
            return redirect('dashboard', community_id=community_id)

        return render(request, 'savannahv2/manager_edit.html', view.context)

class ManagerPasswordChange(SavannahView):
    def __init__(self, request, community_id):
        super(ManagerPasswordChange, self).__init__(request, community_id)
        self.community = get_object_or_404(Community, id=community_id)
        self.manager = get_object_or_404(ManagerProfile, community=self.community, user=request.user)
        self.active_tab = "community"
        self._form = None

    @property 
    def form(self):
        if self._form is None:
            if self.request.method == 'POST':
                self._form = PasswordChangeForm(user=self.request.user, data=self.request.POST)
            else:
                self._form = PasswordChangeForm(user=self.request.user)
        return self._form

    @login_required
    def as_view(request, community_id):
        view = ManagerPasswordChange(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            user = view.form.save()
            login_user(request, user)
            messages.success(request, "Your password has been changed")
            return redirect('manager_preferences', community_id=community_id)

        return render(request, 'savannahv2/password_change.html', view.context)

class ManagerDelete(SavannahView):
    def __init__(self, request, community_id):
        super(ManagerDelete, self).__init__(request, community_id)
        self.community = get_object_or_404(Community, id=community_id)
        self.manager = get_object_or_404(ManagerProfile, community=self.community, user=request.user)
        self.active_tab = "community"
        self._form = None

    @property
    def other_managers(self):
        if self.community.managers is not None:
            return self.community.managers.user_set.exclude(id=self.request.user.id)
        else:
            return {'count': 0}

    @property
    def is_owner(self):
        return self.community.owner == self.request.user

    @login_required
    def as_view(request, community_id):
        view = ManagerDelete(request, community_id)
        if request.method == "POST":
            if view.is_owner:
                if 'new_owner' not in request.POST or not request.POST.get('new_owner', 0):
                    messages.error(request, "You must select a new owner before leaving")
                    return redirect('manager_delete', community_id=community_id)
                else:
                    new_owner = get_object_or_404(User, id=request.POST.get('new_owner'))
                    view.community.owner = new_owner
                    view.community.save()

            if view.community.managers is not None:
                view.community.managers.user_set.remove(request.user)
            view.manager.delete()

            return redirect('home')

        return render(request, "savannahv2/manager_leave.html", view.context)

class EditCommunity(SavannahView):

    def __init__(self, request, community_id):
        super(EditCommunity, self).__init__(request, community_id)
        self.community = get_object_or_404(Community, id=community_id)
        self.active_tab = "community"
        self._form = None

    @property 
    def form(self):
        if self._form is None:
            if self.request.method == 'POST':
                self._form = CommunityForm(instance=self.community, data=self.request.POST, files=self.request.FILES)
            else:
                self._form = CommunityForm(instance=self.community)
        return self._form

    @login_required
    def as_view(request, community_id):
        view = EditCommunity(request, community_id)
        if request.method == "POST" and view.form.is_valid():
            community = view.form.save()
            messages.success(request, "Community information updated")
            return redirect('managers', community_id=community_id)

        return render(request, 'savannahv2/community_edit.html', view.context)