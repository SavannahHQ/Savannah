from django.core.management.base import BaseCommand, CommandError
import datetime
import re
from perceval.backends.core.slack import Slack
from corm.models import Community, Source, Member, Contact, Channel, Conversation

class Command(BaseCommand):
    help = 'Import data from Slack sources'

    def handle(self, *args, **options):
      print("Importing Slack data")

      for channel in Channel.objects.filter(source__connector="corm.plugins.slack"):
        if channel.origin_id and channel.source.auth_secret:
          import_slack(channel)

def import_slack(channel):
  print("Importing from %s" % channel)
  source = channel.source
  community = source.community
  slack = Slack(channel.origin_id, channel.source.auth_secret)
  items = [i for i in slack.fetch()]
  for slack_id, user in slack._users.items():
      if not user.get('is_bot'):
        slack_user_id = "slack.com/%s" % slack_id
        member, created = Member.objects.get_or_create(community=community, name=user.get('real_name'))
        Contact.objects.get_or_create(origin_id=slack_user_id, defaults={'member':member, 'source':source, 'detail':user.get('name')})

  tag_matcher = re.compile('\<\@([^>]+)\>')
  for item in items:
    if item.get('data').get('subtype') is None and item.get('data').get('user_data'):
      tagged = set(tag_matcher.findall(item.get('data').get('text')))
      if len(tagged) > 0:
        #print("Importing conversation from %s" % item.get('data').get('user_data').get('name'))
        slack_user_id = "slack.com/%s" % item.get('data').get('user_data').get('id')
        contact = Contact.objects.get(origin_id=slack_user_id)
        tstamp = datetime.datetime.fromtimestamp(float(item.get('data').get('ts')))
        convo_text = item.get('data').get('text')
        for tagged_user in tagged:
          if slack._users.get(tagged_user):
              convo_text = convo_text.replace("<@%s>"%tagged_user, "@%s"%slack._users.get(tagged_user).get('real_name'))
        convo_text = item.get('data').get('user_data').get('real_name') + ": " + convo_text
        slack_convo_id = "slack.com/conversation/%s" % item.get('data').get('client_msg_id')
        server = source.server or "slack.com"
        slack_convo_link = "https://%s/archives/%s/p%s" % (server, channel.origin_id, item.get('data').get('ts').replace(".", ""))
        convo, created = Conversation.objects.update_or_create(origin_id=slack_convo_id, defaults={'channel':channel, 'content':convo_text, 'timestamp':tstamp, 'location':slack_convo_link})
        convo.participants.add(contact.member)
        for tagged_user in tagged:
          if not slack._users.get(tagged_user):
            print("Unknown Slack user: %s" % tagged_user)
            continue
          #print("Checking for %s" % tagged_user)
          try:
            tagged_user_id = "slack.com/%s" % tagged_user
            tagged_contact = Contact.objects.get(origin_id=tagged_user_id)
            convo.participants.add(tagged_contact.member)
          except:
            print("Failed to find Contact for %s" % slack._users.get(tagged_user).get('name'))
          try:
            if not contact.member.is_connected(tagged_contact.member):
              contact.member.add_connection(tagged_contact.member, source, tstamp)
          except Exception as e:
            print("Failed to make connection between %s and %s" % (contact.member, tagged_contact.member))
            print(e)
