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

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity')
        community_id = options.get('community_id')
        if community_id:
            communities = [Community.objects.get(id=community_id)]
        else:
            communities = Community.objects.filter(status=Community.ACTIVE)


        for community in communities:
            community_start = datetime.datetime.utcnow()
            default_project, created = Project.objects.get_or_create(community=community, default_project=True, defaults={'name': community.name, 'owner':None, 'threshold_user':1, 'threshold_participant':10, 'threshold_contributor':1, 'threshold_core':10})
            other_projects = Project.objects.filter(community=community, default_project=False)

            # Check community-wide levels
            print("Checking member levels for %ss" % community.name)
            now = datetime.datetime.utcnow()
            MemberLevel.objects.filter(community=community, project=default_project, timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)).delete()
            if self.verbosity >= 3:
                print("Default project level deletes: %ss" % (datetime.datetime.utcnow() - now).total_seconds())

            now = datetime.datetime.utcnow()
            speaker_filter=Q(speaker_in__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period))
            for member in Member.objects.filter(community=community).annotate(convo_count=Count('speaker_in__id', filter=speaker_filter, distinct=True), last_convo=Max('speaker_in__timestamp', filter=speaker_filter)):
                if member.convo_count >= default_project.threshold_participant:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.PARTICIPANT, 'timestamp':member.last_convo, 'conversation_count':member.convo_count})
                elif member.convo_count >= default_project.threshold_user:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.USER, 'timestamp':member.last_convo, 'conversation_count':member.convo_count})
            if self.verbosity >= 3:
                print("Default project conversation levels: %ss" % (datetime.datetime.utcnow() - now).total_seconds())

            now = datetime.datetime.utcnow()
            author_filter = Q(contribution__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period))
            for member in Member.objects.filter(community=community).annotate(contrib_count=Count('contribution__id', filter=author_filter, distinct=True), last_contrib=Max('contribution__timestamp', filter=author_filter)):
                if member.contrib_count >= default_project.threshold_core:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.CORE, 'timestamp':member.last_contrib, 'contribution_count':member.contrib_count})
                elif member.contrib_count >= default_project.threshold_contributor:
                    MemberLevel.objects.update_or_create(community=community, project=default_project, member=member, defaults={'level':MemberLevel.CONTRIBUTOR, 'timestamp':member.last_contrib, 'contribution_count':member.contrib_count})
            if self.verbosity >= 3:
                print("Default project contribution levels: %ss\n" % (datetime.datetime.utcnow() - now).total_seconds())

            # Check per-project levels
            for project in other_projects:
                print("Checking member levels for %s / %s" % (community.name, project.name))
                now = datetime.datetime.utcnow()
                MemberLevel.objects.filter(community=community, project=project, timestamp__lt=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)).delete()
                if self.verbosity >= 3:
                    print("%s project level deletes: %ss" % (project.name, (datetime.datetime.utcnow() - now).total_seconds()))

                now = datetime.datetime.utcnow()
                speaker_filter=Q(speaker_in__channel__in=project.channels.all())
                if project.tag is not None:
                    speaker_filter = speaker_filter | Q(speaker_in__tags=project.tag)
                for member in Member.objects.filter(community=community).filter(speaker_in__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=project.threshold_period)).annotate(convo_count=Count('speaker_in__id', filter=speaker_filter, distinct=True), last_convo=Max('speaker_in__timestamp', filter=speaker_filter)):
                    if member.convo_count >= project.threshold_participant:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.PARTICIPANT, 'timestamp':member.last_convo, 'conversation_count':member.convo_count})
                    elif member.convo_count >= project.threshold_user:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.USER, 'timestamp':member.last_convo, 'conversation_count':member.convo_count})
                if self.verbosity >= 3:
                    print("%s project conversation levels: %ss" % (project.name, (datetime.datetime.utcnow() - now).total_seconds()))

                now = datetime.datetime.utcnow()
                author_filter = Q(contribution__channel__in=project.channels.all())
                if project.tag is not None:
                    author_filter = author_filter | Q(contribution__tags=project.tag)
                for member in Member.objects.filter(community=community).filter(contribution__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=project.threshold_period)).annotate(contrib_count=Count('contribution__id', filter=author_filter, distinct=True), last_contrib=Max('contribution__timestamp', filter=author_filter)):
                    if member.contrib_count >= project.threshold_core:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.CORE, 'timestamp':member.last_contrib, 'contribution_count':member.contrib_count})
                    elif member.contrib_count >= project.threshold_contributor:
                        MemberLevel.objects.update_or_create(community=community, project=project, member=member, defaults={'level':MemberLevel.CONTRIBUTOR, 'timestamp':member.last_contrib, 'contribution_count':member.contrib_count})
                if self.verbosity >= 3:
                    print("%s project contribition levels: %ss\n" % (project.name, (datetime.datetime.utcnow() - now).total_seconds()))

            if self.verbosity >= 3:
                print("Time checking %s: %ss\n" % (community, (datetime.datetime.utcnow() - community_start).total_seconds()))
