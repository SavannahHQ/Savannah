import uuid
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import get_random_string
from django.template.loader import get_template, render_to_string
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, reverse
from django.core.serializers.json import DjangoJSONEncoder

from corm.models import Community, Member, ManagerProfile, Tag, Company, Source, Channel
from corm.email import EmailMessage, send_message, remaining_emails_allowed

import datetime

class EmailRecord(models.Model):
    """
    Model to store all the outgoing emails.
    """

    when = models.DateTimeField(null=False, auto_now_add=True)
    sender = models.ForeignKey(
        User,
        related_name="sent_messages_old",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    member = models.ForeignKey(
        Member,
        related_name="recv_messages_old",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    email = models.EmailField(null=False, blank=False)
    category = models.CharField(null=False, max_length=128)
    subject = models.CharField(null=False, max_length=128)
    body = models.TextField(null=False, max_length=1024)
    ok = models.BooleanField(null=False, default=True)


class ManagerInviteEmail(EmailMessage):
    def __init__(self, invite):
        super(ManagerInviteEmail, self).__init__(invite.invited_by, invite.community)
        self.subject = "You've been invited to manage %s on Savannah" % self.community.name
        self.category = "manager_invite"
        self.context.update({
            'confirmation_key': invite.key,
            'expiration': invite.expires
        })

        self.text_body = "emails/invitation_to_manage.txt"
        self.html_body = "emails/invitation_to_manage.html"


class ManagerInvite(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    invited_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    email = models.EmailField()
    timestamp = models.DateTimeField(auto_now_add=True)
    key = models.CharField(max_length=256)
    expires = models.DateTimeField()

    @classmethod
    def send(cls, community, inviter, email):
        valid_for = getattr(settings, "EMAIL_CONFIRMAION_EXPIRATION_DAYS", 5)
        invite, created = ManagerInvite.objects.update_or_create(
            community=community,
            email=email,
            defaults={
                "invited_by": inviter,
                "key": get_random_string(length=32),
                "expires": datetime.datetime.utcnow() + datetime.timedelta(days=valid_for)
            }
        )
        msg = ManagerInviteEmail(invite)
        msg.send(email)


class PasswordResetEmail(EmailMessage):
    def __init__(self, request):
        system_user = get_object_or_404(User, username=settings.SYSTEM_USER)
        super(PasswordResetEmail, self).__init__(system_user)
        self.subject = "Password reset for %s" % settings.SITE_NAME
        self.category = "password_reset"
        self.context.update({
            'reset_key': request.key,
            'expiration': request.expires
        })
        self.text_body = "emails/password_reset_email.txt"
        self.html_body = "emails/password_reset_email.html"


class PasswordResetRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    timestamp = models.DateTimeField(auto_now_add=True)
    key = models.CharField(max_length=256)
    expires = models.DateTimeField()

    @classmethod
    def send(cls, email):
        email = email.lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.MultipleObjectsReturned:
            user = User.objects.filter(email__iexact=email).order_by('-last_login').first()
        except User.DoesNotExist:
            try:
                manager = ManagerProfile.objects.get(contact_email__iexact=email)
                user = manager.user
            except ManagerProfile.DoesNotExist:
                # No matching user, silently ignore
                return

        valid_for = getattr(settings, "PASSWORD_RESET_EXPIRATION_DAYS", 1)
        request, created = PasswordResetRequest.objects.update_or_create(
            user=user,
            email=email,
            defaults={
                "key": get_random_string(length=32),
                "expires": datetime.datetime.utcnow() + datetime.timedelta(days=valid_for)
            }
        )
        msg = PasswordResetEmail(request)
        msg.send(email)

class PublicDashboard(models.Model):
    OVERVIEW = 'overview'
    MEMBERS = 'members'
    CONVERSATIONS = 'conversations'
    CONTRIBUTIONS = 'contributions'
    CONTRIBUTORS = 'contributors'
    REPORT = 'report'
    PAGES = {
        OVERVIEW: "Overview",
        MEMBERS: "Members",
        CONVERSATIONS: "Conversations",
        CONTRIBUTIONS: "Contributions",
        CONTRIBUTORS: "Contributors",
        REPORT: "Report",
    }
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    page = models.CharField(max_length=32, choices=PAGES.items())
    display_name = models.CharField(max_length=256, default="", blank=False, null=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveBigIntegerField(default=0)
    show_companies = models.BooleanField(default=False, help_text="Show company names.")
    show_members = models.BooleanField(default=False, help_text="Show member names and affiliation (but not contact info).")
    pin_time = models.BooleanField(default=False, help_text="Show data from the time the dashboard was shared, not the time it was viewed.")
    filters = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    def get_absolute_url(self):
        return reverse("public_%s" % self.page, kwargs={"dashboard_id": self.id})
    
    def count(self):
        self.view_count += 1
        self.save()

    def apply(self, view):
        view.community = self.community

        filters = self.filters

        view.tag = None
        if 'tag' in filters and filters['tag'] is not None:
            view.tag = Tag.objects.get(community=view.community, name=filters.get('tag'))

        view.member_tag = None
        if 'member_tag' in filters and filters['member_tag'] is not None:
            view.member_tag = Tag.objects.get(community=view.community, name=filters.get('member_tag'))

        view.member_company = None
        if 'member_company' in filters and filters['member_company'] is not None:
            view.member_company = Company.objects.get(community=view.community, id=filters.get('member_company'))

        view.role = None
        if 'member_role' in filters and filters['member_role'] is not None:
            view.role = filters.get('member_role')

        view.contrib_type = None
        if 'contrib_type' in filters and filters['contrib_type'] is not None:
            view.contrib_type = filters.get('contrib_type')

        view.source = None
        if 'source' in filters and filters['source'] is not None:
            source_id = int(filters.get('source'))
            if source_id < 0:
                view.exclude_source = True
                source_id = abs(source_id)
            view.source = Source.objects.get(community=view.community, id=source_id)

        view.rangestart = None
        view.rangeend = None
        view.timespan = getattr(view, 'MAX_TIMESPAN', 365)
        if 'timespan' in filters and filters['timespan'] is not None:
            view.timespan = filters.get('timespan')
            view.rangestart = datetime.datetime.utcnow() - datetime.timedelta(days=view.timespan)
            view.rangeend = datetime.datetime.utcnow()

        if self.pin_time:
            if 'rangeend' in filters and filters.get('rangeend') is not None:
                view.rangeend = datetime.datetime.strptime(filters.get('rangeend'), view.DATE_FORMAT)
            else:
                view.rangeend = self.created_at
            if 'rangestart' in filters and filters.get('rangestart') is not None:
                view.rangestart = datetime.datetime.strptime(filters.get('rangestart'), view.DATE_FORMAT)
            else:
                view.rangestart = view.rangeend - datetime.timedelta(days=view.timespan)
            view.timespan = (view.rangeend - view.rangestart).days

        if 'sort_by' in filters and filters['sort_by'] is not None:
            view.sort_by = filters.get('sort_by')
            
        context = view.context
        context['dashboard'] = self
        return context
