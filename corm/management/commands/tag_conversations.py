from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from perceval.backends.core.slack import Slack
from corm.models import Tag, Conversation, Community

PUNCTUATION = "!\"&'()*+,.:;<=>?@[\]^_`{|}~"

class Command(BaseCommand):
    help = 'Auto-Tag conversations based on Tag keywords'

    def handle(self, *args, **options):

      for community in Community.objects.all():
        print("Tagging conversations in  %s" % community.name)
        keywords = dict()
        for tag in community.tag_set.filter(keywords__isnull=False):
          for word in tag.keywords.split(","):
            word = " "+word.lower().strip()+" "
            if not word in keywords:
              keywords[word] = set()
            keywords[word].add(tag)
        #print("Found %s keywords" % len(keywords))

        for convo in Conversation.objects.filter(channel__source__community=community):
          table = str.maketrans(PUNCTUATION, ' '*len(PUNCTUATION))
          text = " "+convo.content.lower().translate(table)+" "
          tagged = set()
          for keyword in keywords:
            if keyword in text:
              for tag in keywords[keyword]:
                if tag.id not in tagged:
                  #print("Tagging \"%s\" with %s because of %s" % (convo, tag.name, keyword))
                  convo.tags.add(tag)
                  tagged.add(tag.id)
