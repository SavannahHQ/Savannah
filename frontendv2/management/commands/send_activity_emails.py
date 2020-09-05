from django.core.management.base import BaseCommand, CommandError
import operator
import json
import datetime, calendar
import dateutil.parser

from django.shortcuts import reverse
from django.db.models import F, Q, Count, Max, Min
from django.db.models.functions import Trunc
from django.core.serializers.json import DjangoJSONEncoder


from corm.models import Community, ManagerProfile, Member, Conversation, Tag, Contact, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag
from corm.models import pluralize
from frontendv2.models import EmailMessage, EmailRecord
from notifications.signals import notify

class MisssedActivityEmail(EmailMessage):
    def __init__(self, manager):
        super(MisssedActivityEmail, self).__init__(manager.user, manager.community)
        self.subject = "Here's what you've missed in %s" % self.community.name
        self.category = "missed_activity"

        self.text_body = "emails/missed_activity.txt"
        self.html_body = "emails/missed_activity.html"

class Command(BaseCommand):
    help = 'Sends missed activity emails to Community Managers'

    def handle(self, *args, **options):
        self.email_count = 0
        for manager in ManagerProfile.objects.filter(send_notifications=True, user__email__isnull=False).order_by('-last_seen'):
            self.send_missed_activity_report(manager)

        print("Sent %s emails" % self.email_count)

    def send_missed_activity_report(self, manager):
        community = manager.community
        start = manager.last_seen
        end = datetime.datetime.utcnow()

        new_members = self.get_new_members(community, start, end)
        new_contributors = self.get_new_contributors(community, start, end)

        if new_members.count() > 0 or new_contributors.count() > 0:
            msg = MisssedActivityEmail(manager)
            msg.context.update({
                'last_seen': manager.last_seen,
                'new_members': new_members,
                'new_contributors': new_contributors
            })
            msg.send(manager.user.email)
            self.email_count += 1


    def get_new_members(self, community, start, end):
        return Member.objects.filter(community=community, first_seen__gt=start, first_seen__lte=end).order_by('-first_seen')

    def get_new_contributors(self, community, start, end):
        members = Member.objects.filter(community=community)
        members = members.annotate(first_contrib=Min('contribution__timestamp'))
        members = members.filter(first_contrib__gt=start, first_contrib__lte=end).order_by('-first_contrib')
        return members