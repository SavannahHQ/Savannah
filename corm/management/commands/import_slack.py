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
        contact_matches = Contact.objects.filter(origin_id=slack_user_id, source=source)
        if contact_matches.count() == 0:
          member = Member.objects.create(community=community, name=user.get('real_name'))
          Contact.objects.get_or_create(origin_id=slack_user_id, defaults={'member':member, 'source':source, 'detail':user.get('name')})

  tag_matcher = re.compile('\<\@([^>]+)\>')
  for item in items:
    if item.get('data').get('subtype') is None and item.get('data').get('user_data'):
      tagged = set(tag_matcher.findall(item.get('data').get('text')))
      if len(tagged) > 0 or 'thread_ts' in item.get('data'):
        #print("Importing conversation from %s" % item.get('data').get('user_data').get('name'))
        slack_user_id = "slack.com/%s" % item.get('data').get('user_data').get('id')
        contact = Contact.objects.get(origin_id=slack_user_id)
        tstamp = datetime.datetime.fromtimestamp(float(item.get('data').get('ts')))
        slack_convo_id = "slack.com/conversation/%s" % item.get('data').get('client_msg_id')
        server = source.server or "slack.com"
        slack_convo_link = "https://%s/archives/%s/p%s" % (server, channel.origin_id, item.get('data').get('ts').replace(".", ""))
        thread = None
        if 'thread_ts' in item.get('data'):
          if item.get('data').get('ts') == '1586966084.225900':
            #https://influxcommunity.slack.com/archives/CH7C56X4Z/p1586966084225900?thread_ts=1586965678.225100&cid=CH7C56X4Z
            pass#import pdb; pdb.set_trace()
          slack_convo_link = slack_convo_link + "?thread_ts=%s&cid=%s" % (item.get('data').get('thread_ts'), channel.origin_id)
          slack_thread_link = "https://%s/archives/%s/p%s" % (server, channel.origin_id, item.get('data').get('thread_ts').replace(".", ""))
          slack_thread_link = slack_thread_link + "?thread_ts=%s&cid=%s" % (item.get('data').get('thread_ts'), channel.origin_id)
          try:
            thread = Conversation.objects.get(channel=channel, location=slack_thread_link)
          except:
            print("Can't find thread, or more than one record for thread: %s" % slack_thread_link)
            pass
        
        if thread is not None:
          thread.participants.add(contact.member)

        convo_text = item.get('data').get('text')
        for tagged_user in tagged:
          if slack._users.get(tagged_user):
              convo_text = convo_text.replace("<@%s>"%tagged_user, "@%s"%slack._users.get(tagged_user).get('real_name'))
        convo_text = item.get('data').get('user_data').get('real_name') + ": " + convo_text
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
            if thread is not None:
              thread.participants.add(tagged_contact.member)
          except:
            print("Failed to find Contact for %s" % slack._users.get(tagged_user).get('name'))
          try:
            contact.member.add_connection(tagged_contact.member, source, tstamp)
          except Exception as e:
            print("Failed to make connection between %s and %s" % (contact.member, tagged_contact.member))
            print(e)

        # Connect this conversation's speaker to everyone else in this thread
        if thread is not None:
          for thread_member in thread.participants.all():
            try:
              contact.member.add_connection(thread_member, source, tstamp)
              convo.participants.add(thread_member)
            except Exception as e:
              print("Failed to make connection between %s and %s" % (contact.member, tagged_contact.member))
              print(e)
