from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import get_random_string
from django.template.loader import get_template, render_to_string
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404

from corm.models import Community, Member, ManagerProfile

import datetime

class EmailMessage(object):
    def __init__(self, sender, community=None):
        self.sender = sender
        self.community = community
        self.category = None
        self.subject = None
        self.text_body = None
        self.html_body = None
        self.member = None
        self.context = {
            "community": self.community,
            "sender": self.sender,
            "SITE_ROOT": getattr(settings, 'SITE_ROOT', ''),
            "SITE_NAME": getattr(settings, 'SITE_NAME', ''),
        }

    def send(self, to):
        if not isinstance(to, list):
            to = [to]
        if self.sender is None or self.category is None or self.subject is None or self.text_body is None or self.html_body is None:
            raise NotImplementedError

        for email in to:
            if isinstance(email, tuple) and len(email) > 1:
                email = email[1]
            send_message(
                self.sender,
                self.category,
                email,
                self.subject,
                self.render_text(self.text_body),
                self.render_text(self.html_body),
                self.member
            )

    def render_text(self, template):
        return render_to_string(template, self.context)

class EmailRecord(models.Model):
    """
    Model to store all the outgoing emails.
    """

    when = models.DateTimeField(null=False, auto_now_add=True)
    sender = models.ForeignKey(
        User,
        related_name="sent_messages",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    member = models.ForeignKey(
        Member,
        related_name="recv_messages",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    email = models.EmailField(null=False, blank=False)
    category = models.CharField(null=False, max_length=128)
    subject = models.CharField(null=False, max_length=128)
    body = models.TextField(null=False, max_length=1024)
    ok = models.BooleanField(null=False, default=True)

def remaining_emails_allowed(user):
    recently_sent = EmailRecord.objects.filter(
        sender=user,
        when__gte=datetime.datetime.now() - datetime.timedelta(hours=24),
    ).count()
    if recently_sent < settings.ALLOWED_EMAILS_PER_DAY:
        return settings.ALLOWED_EMAILS_PER_DAY - recently_sent
    else:
        return 0

def send_message(sender, category, to, subject, text_body, html_body, member=None):
    email_from = getattr(
        settings, "DEFAULT_FROM_EMAIL", "noreply@savannahhq.com"
    )

    success = send_mail(
        from_email=email_from,
        html_message=html_body,
        message=text_body,
        recipient_list=[to],
        subject=subject,
        fail_silently=True,
    )

    EmailRecord.objects.create(
        sender=sender,
        member=member,
        email=to,
        category=category,
        subject=subject,
        body=text_body,
        ok=success,
    )

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
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            try:
                manager = ManagerProfile.objects.get(contact_email=email)
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

