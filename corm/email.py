
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import get_random_string
from django.template.loader import get_template, render_to_string
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404

from corm.models import Community, Member, EmailRecord

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
