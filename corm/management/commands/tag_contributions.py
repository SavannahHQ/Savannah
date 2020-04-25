from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from perceval.backends.core.slack import Slack
from corm.models import Tag, Contribution, Community

PUNCTUATION = "!\"&'()*+,.:;<=>?@[\]^_`{|}~/\r\n"

class Command(BaseCommand):
    help = 'Auto-Tag contributions based attached conversations'

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

        for contrib in Contribution.objects.filter(community=community, conversation__isnull=False):
          if contrib.conversation.tags.count() > 0:
            #print("Tagging: %s" % contrib)
            contrib.tags.set(contrib.conversation.tags.all())
          
