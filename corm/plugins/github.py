import datetime
import re
import requests
from django.conf import settings
from corm.plugins import BasePlugin, PluginImporter
from corm.models import *

GITHUB_ISSUES_URL = 'https://api.github.com/repos/%(owner)s/%(repo)s/issues?state=all&since=%(since)s&page=%(page)s'
GITHUB_REPOS_URL = 'https://api.github.com/orgs/%(owner)s/repos?sort=pushed&direction=desc'
GITHUB_TIMESTAMP = '%Y-%m-%dT%H:%M:%SZ'

class GithubPlugin(BasePlugin):

    def get_identity_url(self, contact):
        return "https://github.com/%s" % contact.detail

    def get_source_type_name(self):
        return "Github"

    def get_import_command_name(self):
        return "github"


    def get_source_importer(self, source):
        return GithubImporter(source)

    def get_channels(self, source):
        channels = []

        headers = {'Authorization': 'token %s' % source.auth_secret}
        resp = requests.get(GITHUB_REPOS_URL % {'owner': source.auth_id}, headers=headers)   
        if resp.status_code == 200:
            data = resp.json()
            for repo in data:
                channels.append({
                    'id': repo.get('html_url'),
                    'name': repo.get('name'),
                    'topic': repo.get('description'),
                    'count': repo.get('updated_at'),
                })
        else:
            print("Request failed: %s" % resp.content)
        return channels

class GithubImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Authorization': 'token %s' % source.auth_secret,
        }
        self.TIMESTAMP_FORMAT = GITHUB_TIMESTAMP
        self.PR_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Pull Ruest")

    def api_call(self, path):
        if settings.DEBUG:
            print("API Call: %s" % path)
        return self.api_request(path, headers=self.API_HEADERS)

    def import_channel(self, channel):
      source = channel.source
      community = source.community
      github_path = channel.origin_id.split('/')

      owner = github_path[3]
      repo = github_path[4]
      if channel.last_import:
        from_date = channel.last_import.strftime(GITHUB_TIMESTAMP)
      else:
        from_date = datetime.datetime.utcnow() - datetime.timedelta(days=30)
      print("  since %s" % from_date)

      tag_matcher = re.compile('\@([a-zA-Z0-9]+)')
      found_members = dict()

      issues_page = 1
      while (issues_page):
        repo_issues_url = GITHUB_ISSUES_URL % {'owner': owner, 'repo': repo, 'since': from_date, 'page': issues_page}
            
        resp = self.api_call(repo_issues_url)
        if resp.status_code == 200:
            issues = resp.json()
            for issue in issues:

                participants = set()
                conversations = set()
                tstamp = datetime.datetime.strptime(issue['created_at'], GITHUB_TIMESTAMP)
                github_convo_link = issue['url']

                # Add Member
                if issue['user']['login'] in found_members:
                    member = found_members[issue['user']['login']]
                else:
                    github_user_id = 'github.com/%s' % issue['user']['login']
                    contact_matches = Contact.objects.filter(origin_id=github_user_id, source=source)
                    if contact_matches.count() == 0:
                        member = Member.objects.create(community=community, name=issue['user']['login'], date_added=tstamp)
                        contact, created = Contact.objects.get_or_create(origin_id=github_user_id, defaults={'member':member, 'source':source, 'detail':issue['user']['login']})
                    else:
                        contact = contact_matches[0]
                        member = contact.member
                    found_members[issue['user']['login']] = member

                # Pull Requests are an Activity
                if 'pull_request' in issue:
                    activity, created = Contribution.objects.update_or_create(origin_id=github_convo_link, defaults={'contribution_type':self.PR_CONTRIBUTION, 'community':source.community, 'channel':channel, 'author':member, 'timestamp':tstamp, 'title':issue['title'], 'location':issue['html_url']})
                    # Not all comments should get the channel tag, but all PRs should
                    if channel.tag:
                        activity.tags.add(channel.tag)
                else:
                    activity = None

                # If there are comments it's a Conversation
                if issue.get('comments', 0) > 0:
                    convo, created = Conversation.objects.update_or_create(origin_id=github_convo_link, defaults={'channel':channel, 'speaker':member, 'content':issue['body'], 'timestamp':tstamp, 'location':issue['html_url']})
                    conversations.add(convo)
                    if activity:
                        activity.conversation = convo
                        activity.save()

                    participants.add(member)

                    comment_resp = self.api_call(issue['comments_url'])
                    if comment_resp.status_code == 200:
                        comments = comment_resp.json()
                        for comment in comments:
                            comment_tstamp = datetime.datetime.strptime(comment['created_at'], GITHUB_TIMESTAMP)
                            if comment['user']['login'] in found_members:
                                comment_member = found_members[comment['user']['login']]
                            else:
                                comment_user_id = 'github.com/%s' % comment['user']['login']
                                contact_matches = Contact.objects.filter(origin_id=comment_user_id, source=source)
                                if contact_matches.count() == 0:
                                    comment_member = Member.objects.create(community=community, name=comment['user']['login'], date_added=comment_tstamp)
                                    Contact.objects.get_or_create(origin_id=comment_user_id, defaults={'member':comment_member, 'source':source, 'detail':comment['user']['login']})
                                else:
                                    comment_member = contact_matches[0].member
                            comment_convo, created = Conversation.objects.update_or_create(origin_id=comment['url'], defaults={'channel':channel, 'speaker':comment_member, 'content':comment['body'], 'timestamp':comment_tstamp, 'location':comment['html_url'], 'thread_start':convo})
                            participants.add(comment_member)
                            conversations.add(comment_convo)
                            tagged = set(tag_matcher.findall(comment['body']))
                            if tagged:
                                for tagged_user in tagged:
                                    if tagged_user in found_members:
                                        participants.add(found_members[tagged_user])
                                    else:
                                        try:
                                            tagged_user_id = "github.com/%s" % tagged_user
                                            tagged_contact = Contact.objects.get(origin_id=tagged_user_id)
                                            participants.add(tagged_contact.member)
                                        except:
                                            pass#print("    Failed to find Contact for %s" % tagged_user)


                try:
                    tagged = set(tag_matcher.findall(issue['body']))
                    if tagged:
                        for tagged_user in tagged:
                            if tagged_user in found_members:
                                participants.add(found_members[tagged_user])
                            else:
                                try:
                                    tagged_user_id = "github.com/%s" % tagged_user
                                    tagged_contact = Contact.objects.get(origin_id=tagged_user_id)
                                    participants.add(tagged_contact.member)
                                except:
                                    pass#print("    Failed to find Contact for %s" % tagged_user)
                except:
                    pass

                # Add everybody involved as a participant in every conversation
                for convo in conversations:
                    convo.participants.set(participants)

                # Connect all participants
                for from_member in participants:
                    for to_member in participants:
                        if from_member.id != to_member.id:
                            from_member.add_connection(to_member, source, tstamp)


        # If there are more pages of issues, continue on to the next apge
        if 'link' in resp.headers and 'rel="next"' in resp.headers['link']:
            issues_page+= 1
        else:
            break