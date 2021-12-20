from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from django.db.models import Count, Q, F, Value as V, fields, Min
from django.db.models.functions import Concat
from corm.models import Conversation, Community, Source, ConnectionManager, MemberConnection, Participant, Project

class Command(BaseCommand):
    help = 'Auto-Connect participants in conversations'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--source', dest='source_id', type=int)
        parser.add_argument('--connector', dest='connector', type=str)

    def handle(self, *args, **options):

      conversations = Conversation.objects.all()

      community_id = options.get('community_id')
      source_id = options.get('source_id')
      connector = options.get('connector')

      if community_id:
          community = Community.objects.get(id=community_id)
          print("Using Community: %s" % community.name)
          communities = [community]
      else:
          communities = Community.objects.filter(status=Community.ACTIVE)

      if source_id:
          source = Source.objects.get(id=source_id)
          print("Using Source: %s" % source.name)
          conversations = conversations.filter(channel__source=source)

      if connector:
          print("Using Connector: %s" % ConnectionManager.display_name(connector))
          conversations = conversations.filter(channel__source__connector=connector)

      for community in communities:
        print("Connecting %s..." % community.name)
        # Remove self-connections
        print("Removing self-connections")
        selfcon = MemberConnection.objects.filter(community=community, from_member_id=F('to_member_id'))
        selfcon.delete()

        # Remove duplicates
        print("Removing duplicates")
        connection_pair = Concat('from_member_id', V('-'), 'to_member_id', output_field=fields.CharField())
        dups = MemberConnection.objects.filter(community=community).order_by('from_member_id')
        dups = dups.annotate(conpair=connection_pair)
        dups = dups.values('conpair')
        dups = dups.annotate(dup_count=Count('id'), min_id=Min('id'))
        dups = dups.filter(dup_count__gt=1)
        for con in dups:
            print("Dup: %s" % con)
            from_member_id, to_member_id = con['conpair'].split('-')
            from_member_id = int(from_member_id)
            to_member_id = int(to_member_id)
            MemberConnection.objects.filter(from_member_id=from_member_id, to_member_id=to_member_id, id__gt=con['min_id']).delete()

        default_project = Project.objects.get(community=community, default_project=True)

        # Zero out old connections
        MemberConnection.objects.filter(last_connected__lt=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)).update(connection_count=0)

        # Count connection events
        print("Calculating number of connection")
        found = set()
        participants = Participant.objects.filter(community=community, timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)).exclude(member=F('initiator'))
        participants = participants.values('initiator', 'member').annotate(connection_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=default_project.threshold_period)), distinct=True))
        for connection in participants:
            from_to = "%s-%s" % (connection['initiator'], connection['member'])
            to_from = "%s-%s" % (connection['member'], connection['initiator'])
            if len(found) > 100000:
                print("Dumping found cache")
                found.clear()
            if from_to in found or to_from in found:
                continue
            found.add(from_to)
            found.add(to_from)
            MemberConnection.objects.filter(from_member_id=connection['initiator'], to_member_id=connection['member']).update(connection_count=connection['connection_count'])
            MemberConnection.objects.filter(to_member_id=connection['initiator'], from_member_id=connection['member']).update(connection_count=connection['connection_count'])
