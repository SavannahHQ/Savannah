from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from django.db.models import Count, Q, F, Value as V, fields, Min
from django.db.models.functions import Concat
from corm.models import Conversation, Community, Source, ConnectionManager, MemberConnection

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
        # Remove self-connections
        selfcon = MemberConnection.objects.filter(via__community=community, from_member_id=F('to_member_id'))
        selfcon.delete()

        # Remove duplicates
        connection_pair = Concat('from_member_id', V('-'), 'to_member_id', output_field=fields.CharField())
        dups = MemberConnection.objects.filter(via__community=community).annotate(min_id=Min('id')).values('min_id', 'from_member_id', 'to_member_id')
        dups = dups.annotate(conpair=connection_pair).annotate(dup_count=Count('conpair')).filter(dup_count__gt=1)
        for con in dups:
            MemberConnection.objects.filter(from_member_id=con['from_member_id'], to_member_id=con['to_member_id'], id__gt=con['min_id']).delete()

        # Count connection events
        connections = MemberConnection.objects.filter(via__community=community)
        connections.update(connection_count=1)
        from_date = datetime.datetime.utcnow() - datetime.timedelta(days=182)
        connections = connections.annotate(count=Count('to_member__speaker_in', filter=Q(to_member__speaker_in__timestamp__gt=from_date, to_member__speaker_in__participants=F('from_member'))))
        for connection in connections.values('from_member_id', 'to_member_id', 'count'):
            MemberConnection.objects.filter(from_member_id=connection['from_member_id'], to_member_id=connection['to_member_id'], connection_count__lt=connection['count']).update(connection_count=connection['count'])
            MemberConnection.objects.filter(to_member_id=connection['from_member_id'], from_member_id=connection['to_member_id'], connection_count__lt=connection['count']).update(connection_count=connection['count'])

