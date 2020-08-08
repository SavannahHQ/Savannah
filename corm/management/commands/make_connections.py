from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from corm.models import Conversation, Community, Source, ConnectionManager

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
          conversations = conversations.filter(channel__source__community=community)

      if source_id:
          source = Source.objects.get(id=source_id)
          print("Using Source: %s" % source.name)
          conversations = conversations.filter(channel__source=source)

      if connector:
          print("Using Connector: %s" % ConnectionManager.display_name(connector))
          conversations = conversations.filter(channel__source__connector=connector)

      print("Making connections from %s conversations" % conversations.count())
      for convo in conversations:
          for from_participant in convo.participants.all():
              for to_participant in convo.participants.all():
                  if from_participant.id != to_participant.id and not from_participant.is_connected(to_participant):
                      from_participant.add_connection(to_participant, convo.channel.source, timestamp=convo.timestamp)