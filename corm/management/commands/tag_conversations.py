from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from corm.models import Tag, Conversation, Community

PUNCTUATION = "!\"&'()*+,.:;<=>?@[\]^_`{|}~/\r\n"

class Command(BaseCommand):
    help = 'Auto-Tag conversations based on Tag keywords'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--source', dest='source_id', type=int)
        parser.add_argument('--connector', dest='connector', type=str)
        
    def handle(self, *args, **options):

      community_id = options.get('community_id')
      source_id = options.get('source_id')
      connector = options.get('connector')

      if community_id:
          community = Community.objects.get(id=community_id)
          print("Using Community: %s" % community.name)
          communities = [community]
      else:
          communities = Community.objects.filter(status=Community.ACTIVE)

      past_year = datetime.datetime.utcnow() - datetime.timedelta(days=365)
      for community in communities:
        print("Tagging conversations in  %s" % community.name)
        keywords = dict()
        for tag in community.tag_set.filter(keywords__isnull=False):
          for word in tag.keywords.split(","):
            word = " "+word.lower().strip()+" "
            if len(word) <= 2:
              # The word is blank
              continue
            if not word in keywords:
              keywords[word] = set()
            keywords[word].add(tag)

        conversations = Conversation.objects.filter(channel__source__community=community, timestamp__gte=past_year)
        if source_id:
            conversations = conversations.filter(channel__source_id=source_id)
        if connector:
            conversations = conversations.filter(channel__source__connector=connector)
        count = conversations.count()
        page = 0
        chunk = 10000
        while count > (chunk * page):
          start = chunk * page
          end = start + chunk
          for convo in conversations[start:end]:
            table = str.maketrans(PUNCTUATION, ' '*len(PUNCTUATION))
            if convo.content is None:
              continue
            text = " "+convo.content.lower().translate(table)+" "
            tagged = set()
            for keyword in keywords:
              if keyword in text:
                for tag in keywords[keyword]:
                  if tag.id not in tagged:
                    #print("Tagging \"%s\" with %s because of %s" % (convo, tag.name, keyword))
                    convo.tags.add(tag)
                    convo.activity.tags.add(tag)
                    tagged.add(tag.id)
          page += 1
