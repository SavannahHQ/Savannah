import datetime
import re
from django.contrib import messages
from django import forms
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.contrib.auth.decorators import login_required

from corm.plugins import BasePlugin, PluginImporter
from corm.models import Community, Source, Contribution, ContributionType
from frontendv2.views import SavannahView

DISCOURSE_USER_URL = '/users/%(username)s.json?'
DISCOURSE_EMAIL_URL = '/users/%(username)s/emails.json?'
DISCOURSE_TOPICS_URL = '/c/%(name)s/%(id)s.json?page=%(page)s'
DISCOURSE_POSTS_URL = '/t/%(id)s.json?print=true'
DISCOURSE_POST_URL = '/t/%(id)s/posts.json?'
DISCOURSE_CATEGORIES_URL = '/categories.json'
DISCOURSE_CATEGORY_URL = '/c/%(id)s/show.json'

class DiscourseForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['name', 'server', 'auth_id', 'auth_secret']
        labels = {
            'server': 'Discourse URL',
            'auth_id': 'Discourse username',
            'auth_secret': 'Discourse API key',
        }
    def __init__(self, *args, **kwargs):
        super(DiscourseForm, self).__init__(*args, **kwargs)
        self.fields['server'].required = True
        self.fields['auth_id'].required = True
        self.fields['auth_secret'].required = True

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    @login_required
    def as_view(request):
        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.discourse", icon_name="fab fa-discourse")
        if request.method == "POST":
            form = DiscourseForm(data=request.POST, instance=new_source)
            if form.is_valid():
                # TODO: attempt API call to validate
                source = form.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        form = DiscourseForm(instance=new_source)
        context = view.context
        context.update({
            'source_form': form,
            'source_plugin': 'Discourse',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, 'savannahv2/source_add.html', context)

urlpatterns = [
    path('auth', SourceAdd.as_view, name='discourse_auth'),
]

class DiscoursePlugin(BasePlugin):

    def get_identity_url(self, contact):
        return "%s/u/%s" % (contact.source.server, contact.detail)

    def get_auth_url(self):
        return reverse('discourse_auth')

    def get_source_type_name(self):
        return "Discourse"

    def get_import_command_name(self):
        return "discourse"

    def get_source_importer(self, source):
        return DiscourseImporter(source)

    def get_channels(self, source):
        importer = DiscourseImporter(source)
        channels = []
        resp = importer.api_call(DISCOURSE_CATEGORIES_URL)
        if resp.status_code == 403:
            # Attempt to lookup public categories
            resp = importer.api_request(source.server+DISCOURSE_CATEGORIES_URL, headers={})

        if resp.status_code == 200:
            data = resp.json()
            for category in data.get('category_list').get('categories'):
                channels.append({
                    'id': '%s/c/%s/%s' % (source.server, category.get('slug'), category.get('id')),
                    'name': category.get('name'),
                    'topic': category.get('description_text'),
                    'count': category.get('topics_all_time'),
                    'is_private': category.get('read_restricted')
                })
                subcategories = category.get('subcategory_ids')
                if subcategories:
                    for sub_id in subcategories:
                        resp = importer.api_call(DISCOURSE_CATEGORY_URL % {'id': sub_id})
                        if resp.status_code == 200:
                            data = resp.json()
                            sub = data.get('category')
                            channels.append({
                                'id': '%s/c/%s/%s/%s' % (source.server, category.get('slug'), sub.get('slug'), sub_id),
                                'name': '%s / %s' % (category.get('name'), sub.get('name')),
                                'topic': sub.get('description_text'),
                                'count': sub.get('topic_count'),
                                'is_private': sub.get('read_restricted')
                            })
        elif resp.status_code == 403:
            raise RuntimeError("Invalid username or token")
        else:
            raise RuntimeError("%s (%s)" % (resp.reason, resp.status_code))
        return channels

class DiscourseImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.API_HEADERS =  {
            'Api-Key': source.auth_secret,
            'Api-Username': source.auth_id,
        }
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
        self.ANSWER_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Support")

    def update_identity(self, identity):
        resp = self.api_call(DISCOURSE_USER_URL % {'username':identity.detail})
        if resp.status_code == 200:
            data = resp.json()
            user = data['user']
            if self.verbosity == 3:
                print(resp.content)
            identity.name = user.get('name', None)
            resp = self.api_call(DISCOURSE_EMAIL_URL % {'username':identity.detail})
            if resp.status_code == 200:
                data = resp.json()
                identity.email_address = data['email']
            identity.save()

            if identity.member.name == identity.detail and identity.name is not None and identity.name != '':
                identity.member.name = identity.name
            if identity.member.email_address is None:
                identity.member.email_address = identity.email_address
            identity.member.save()
        else:
            print("Failed to lookup identity info: %s" % resp.status_code)

    def import_channel(self, channel, from_date, full_import=False):
      source = channel.source
      community = source.community
      discourse_path = channel.origin_id.split('/')

      category_name = discourse_path[-2]
      category_id = int(discourse_path[-1])

      has_more = True
      page = 0
      while (has_more):
        has_more = False
        topics_url = DISCOURSE_TOPICS_URL % {'id': category_id, 'name': category_name, 'page': page}
            
        resp = self.api_call(topics_url)
        if resp.status_code == 200:
            data = resp.json()
            topics = data.get('topic_list').get('topics')
            if len(topics) < 1:
                break
            else:
                page += 1

            for topic in data.get('topic_list').get('topics'):
                if topic['category_id'] != category_id:
                    # Topic belongs to a sub-category
                    continue
                if topic['posts_count'] < 1:
                    # Topic has no posts
                    continue
                if topic['posts_count'] == 1:
                    last_posted = self.strptime(topic['created_at'])
                else:
                    last_posted = self.strptime(topic['last_posted_at'])
                if last_posted < from_date:
                    continue

                # Found a topic to import
                has_more = True
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
                        if thread_post is not None and post_tstamp < from_date:
                            continue
                        post_user_id = post['user_id']
                        post_url = topic_url + '/' + str(post['post_number'])
                        author = self.make_member(post_user_id, post['username'], channel=channel, tstamp=post_tstamp, speaker=True)

                        content = re.sub('<[^<]+?>', '', post['cooked'])
                        post_convo = self.make_conversation(discourse_post_id, channel, author, content=content, tstamp=post_tstamp, location=post_url, thread=thread_post)
                        posts_by_id[discourse_post_id] = post_convo
                        topic_participants.add(author)
                        if thread_post is None:
                            thread_post = post_convo
                            topic_participants.update(list(thread_post.participants.all()))

                        if post.get('accepted_answer') == True: # Removed to allow self-answers // and thread_post.speaker.id != author.id:
                            title = "Answered: %s" % topic['title']
                            activity, created = Contribution.objects.update_or_create(origin_id=discourse_post_id, community=community, defaults={'contribution_type':self.ANSWER_CONTRIBUTION, 'channel':channel, 'author':author, 'timestamp':post_tstamp, 'title':title, 'location':post_url})


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
                        topic_post.participants.add(*topic_participants)

                    if topic_post.participants.count() < 20:
                        # Connect all participants
                        for from_member in topic_post.participants.all():
                            for to_member in topic_participants:
                                if from_member.id != to_member.id:
                                    from_member.add_connection(to_member, self.source, post_tstamp)
                else:
                    print("%s: %s" % (posts_resp.status_code, posts_resp.content))

        else:
            print("%s: %s" % (resp.status_code, resp.content))
            error = resp.json()
            raise RuntimeError("%s: %s" % (error["error_type"], ','.join(error["errors"])))

