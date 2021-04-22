from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from corm.models import Tag, Contribution, Community

PUNCTUATION = "!\"&'()*+,.:;<=>?@[\]^_`{|}~/\r\n"
table = str.maketrans(PUNCTUATION, ' '*len(PUNCTUATION))

class Command(BaseCommand):
    help = 'Auto-Tag contributions based attached conversations'

    def handle(self, *args, **options):

      for community in Community.objects.all():
        print("Tagging contributions in  %s" % community.name)
        keywords = dict()
        for tag in community.tag_set.filter(keywords__isnull=False):
          for word in tag.keywords.split(","):
            word = " "+word.lower().strip()+" "
            if not word in keywords:
              keywords[word] = set()
            keywords[word].add(tag)
        #print("Found %s keywords" % len(keywords))

        for contrib in Contribution.objects.filter(community=community):
          try:
            if contrib.conversation.tags.count() > 0:
              #print("Tagging: %s" % contrib)
              contrib.tags.set(contrib.conversation.tags.all())
              contrib.activity.tags.add(*contrib.conversation.tags.all())
          except:
            pass
          text = " "+contrib.title.lower().translate(table)+" "
          tagged = set()
          for keyword in keywords:
            if keyword in text:
              for tag in keywords[keyword]:
                if tag.id not in tagged:
                  contrib.tags.add(tag)
                  contrib.activity.tags.add(tag)
                  tagged.add(tag.id)