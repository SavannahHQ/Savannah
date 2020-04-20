from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from perceval.backends.core.slack import Slack
from corm.models import Tag, Conversation, Community

class Command(BaseCommand):
    help = 'Auto-Connect participants in conversations'

    def handle(self, *args, **options):

      for convo in Conversation.objects.all():
          for from_participant in convo.participants.all():
              for to_participant in convo.participants.all():
                  if from_participant.id != to_participant.id and not from_participant.is_connected(to_participant):
                      from_participant.add_connection(to_participant, convo.channelsource, timestamp=convo.timestamp)