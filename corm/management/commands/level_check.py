# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import datetime
from django.shortcuts import reverse
from django.db.models import F, Q, Count, Max

from corm.models import Community, Member, Conversation, Contribution, Project, MemberLevel
from corm.models import pluralize
from notifications.signals import notify

LEVEL_RELEVANCY_DAYS = 180

class Command(BaseCommand):
    help = 'Checks member activity and assigns them levels in a project'

    def handle(self, *args, **options):
        for community in Community.objects.all():
            default_project, created = Project.objects.get_or_create(community=community, default_project=True, defaults={'name': community.name, 'owner':None, 'threshold_user':1, 'threshold_participant':10, 'threshold_contributor':1, 'threshold_core':20})
            other_projects = Project.objects.filter(community=community, default_project=False)

            # Check community-wide levels
            print("Checking member levels for %s" % community.name)
            MemberLevel.objects.filter(community=community, project=default_project, timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)).delete()
            for member in Member.objects.filter(community=community).annotate(convo_count=Count('conversation__id', filter=Q(conversation__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)), distinct=True)):
                if member.convo_count >= default_project.threshold_participant:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.PARTICIPANT, 'timestamp':datetime.datetime.utcnow()})
                elif member.convo_count >= default_project.threshold_user:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.USER, 'timestamp':datetime.datetime.utcnow()})

            for member in Member.objects.filter(community=community).annotate(contrib_count=Count('contribution__id', filter=Q(contribution__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)), distinct=True)):
                if member.contrib_count >= default_project.threshold_core:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.CORE, 'timestamp':datetime.datetime.utcnow()})
                elif member.contrib_count >= default_project.threshold_contributor:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.CONTRIBUTOR, 'timestamp':datetime.datetime.utcnow()})

            # Check per-project levels
            for project in other_projects:
                print("Checking member levels for %s / %s" % (community.name, project.name))
                MemberLevel.objects.filter(community=community, project=project, timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)).delete()
                for member in Member.objects.filter(community=community).filter(conversation__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=project.threshold_period)).filter(Q(conversation__channel__in=project.channels.all()) | Q(conversation__tags=project.tag)).annotate(convo_count=Count('conversation__id', distinct=True)):
                    if member.convo_count >= project.threshold_participant:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.PARTICIPANT, 'timestamp':datetime.datetime.utcnow()})
                    elif member.convo_count >= project.threshold_user:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.USER, 'timestamp':datetime.datetime.utcnow()})
                for member in Member.objects.filter(community=community).filter(contribution__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=project.threshold_period)).filter(Q(contribution__channel__in=project.channels.all()) | Q(contribution__tags=project.tag)).annotate(contrib_count=Count('contribution__id', distinct=True)):
                    if member.contrib_count >= project.threshold_core:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.CORE, 'timestamp':datetime.datetime.utcnow()})
                    elif member.contrib_count >= project.threshold_contributor:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.CONTRIBUTOR, 'timestamp':datetime.datetime.utcnow()})
