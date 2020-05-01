import datetime
import re
from corm.plugins import BasePlugin, PluginImporter

DISCOURSE_TOPICS_URL = '/c/%(id)s.json?page=%(page)s'
DISCOURSE_POSTS_URL = '/t/%(id)s.json?print=true'
DISCOURSE_POST_URL = '/t/%(id)s/posts.json?'

class DiscoursePlugin(BasePlugin):

    def get_identity_url(self, contact):
        return "%s/u/%s" % (contact.source.server, contact.detail)

    def get_source_type_name(self):
        return "Discourse"

    def get_import_command_name(self):
        return "discourse"

    def get_source_importer(self, source):
        return DiscourseImporter(source)

class DiscourseImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Api-Key': source.auth_secret,
            'Api-Username': source.auth_id,
        }
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

    def import_channel(self, channel):
      discourse_path = channel.origin_id.split('/')

      category_name = discourse_path[4]
      category_id = discourse_path[5]
      if channel.last_import is None:
        channel.last_import = datetime.datetime.utcnow() - datetime.timedelta(days=182)
      from_date = self.strftime(channel.last_import)
      print("From %s since %s" % (category_name, from_date))

      page = 0
      while (True):
        topics_url = DISCOURSE_TOPICS_URL % {'id': category_id, 'page': page}
            
        resp = self.api_call(topics_url)
        if resp.status_code == 200:
            data = resp.json()
            topics = data.get('topic_list').get('topics')
            if len(topics) < 1:
                break
            else:
                page += 1

            new_topics = 0
            for topic in data.get('topic_list').get('topics'):
                if topic['posts_count'] < 2:
                    continue
                last_posted = self.strptime(topic['last_posted_at'])
                if last_posted < channel.last_import:
                    #print("Old topic: %s" % last_posted)
                    continue
                new_topics += 1
                #print("Importing %s" % topic['title'])
                topic_url = "%s/t/%s/%s" % (self.source.server, topic['slug'], topic['id'])
                topic_participants = set()
                topic_posts = set()
                thread_post = None

                posts_by_id = dict()
                posts_page = 0
                posts_url = DISCOURSE_POSTS_URL % {'id': topic['id'], 'page': posts_page}
                    
                posts_resp = self.api_call(posts_url)

                if posts_resp.status_code == 200:
                    posts_data = posts_resp.json()
                    posts = posts_data['post_stream']['posts']

                    for post in posts:
                        discourse_post_id = post['id']
                        post_tstamp = self.strptime(post['created_at'])
                        post_user_id = post['user_id']
                        post_url = topic_url + '/' + str(post['post_number'])
                        author = self.make_member(post_user_id, post['username'], post_tstamp)

                        content = re.sub('<[^<]+?>', '', post['cooked'])
                        post_convo = self.make_conversation(discourse_post_id, channel, author, content=content, tstamp=post_tstamp, location=post_url, thread=thread_post)
                        posts_by_id[discourse_post_id] = post_convo
                        topic_participants.add(author)
                        if thread_post is None:
                            thread_post = post_convo

                        
                    # post_ids = "&post_ids[]=".join([str(post_id) for post_id in posts_by_id.keys()])
                    # content_resp = self.api_call(DISCOURSE_POST_URL%{'id':topic['id']} + "post_ids[]="+post_ids)
                    # import pdb; pdb.set_trace()
                    # if content_resp.status_code == 200:
                    #     content_data = content_resp.json()
                    #     for post in content_data['post_stream']['posts']:
                    #         if 'raw' in post and post['id'] in posts_by_id:
                    #             posts_by_id[post['id']].content = post['raw']
                    #             posts_by_id[post['id']].save()

                    for topic_post in posts_by_id.values():
                        topic_post.participants.set(topic_participants)

                else:
                    print("%s: %s" % (posts_resp.status_code, posts_resp.content))

            # No new topics in the last page, so don't keep checking
            if new_topics == 0:
                break
        else:
            print("%s: %s" % (resp.status_code, resp.content))

