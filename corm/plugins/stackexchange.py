import datetime
import re
from time import sleep

from corm.models import *
from corm.plugins import BasePlugin, PluginImporter
from frontendv2.views import SavannahView

from urllib.parse import urlparse, parse_qs, urlencode
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.urls import path
from django.contrib import messages
from django import forms
import requests

API_BASE_PATH = 'https://api.stackexchange.com'
AUTHORIZATION_BASE_URL = 'https://stackexchange.com/oauth'
TOKEN_URL = 'https://stackexchange.com/oauth/access_token'
SELF_SITES_URL = '/2.2/me/associated?key=%(access_key)s&access_token=%(access_token)s'
SITE_TAGS_URL = '/2.2/me/tags?site=%(site)s&key=%(access_key)s&access_token=%(access_token)s'
SITE_ALL_TAGS_URL = '/2.2/tags?site=%(site)s&key=%(access_key)s&access_token=%(access_token)s'
SITE_SEARCH_TAGS_URL = '/2.2/tags?inname=%(search)s&site=%(site)s&key=%(access_key)s&access_token=%(access_token)s'
SITE_QUESTIONS_URL = '/2.2/questions/?order=desc&sort=activity&filter=withbody&min=%(from_date)s&tagged=%(tag)s&page=%(page)s'
SITE_ANSWERS_URL = '/2.2/questions/%(question_id)s/answers?order=desc&sort=activity&filter=withbody&min=%(from_date)s&page=%(page)s'
SITE_COMMENTS_URL = '/2.2/posts/%(question_id)s/comments?order=desc&sort=creation&filter=withbody&min=%(from_date)s&page=%(page)s'

class StackExchangeSiteForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ['auth_id']
        labels = {
            'auth_id': 'Site',
        }
        widgets = {
            'auth_id': forms.Select(),
        }
    class Media:
        js = ('js/form_other_field.js',)
    
    def __init__(self, *args, **kwargs):
        super(StackExchangeSiteForm, self).__init__(*args, **kwargs)
        self.fields['auth_id'].required = True
        self.fields['other'] = forms.CharField(label="StackExchange site URL", required=False)

class SourceAdd(SavannahView):
    def _add_sources_message(self):
        pass

    def as_view(request):
        try:
            cred = UserAuthCredentials.objects.get(user=request.user, connector="corm.plugins.stackexchange")
        except UserAuthCredentials.DoesNotExist:
            return authenticate(request)


        view = SourceAdd(request, community_id=request.session['community'])
        new_source = Source(community=view.community, connector="corm.plugins.stackexchange", server="https://stackexchange.com/", auth_id=cred.auth_id, auth_secret=cred.auth_secret, icon_name="fab fa-stack-overflow")

        if request.method == "POST":
            form = StackExchangeSiteForm(data=request.POST, instance=new_source)
            if form.is_valid():
                source = form.save(commit=False)
                if source.auth_id == 'other':
                    stackexchange_url = form.cleaned_data['other']
                    url_parts = urlparse(stackexchange_url)
                    source.auth_id = url_parts.netloc
                    source.server = 'https://'+ url_parts.netloc
                source.name = source.auth_id
                site_names = {}
                resp = requests.get(API_BASE_PATH + SELF_SITES_URL % {'access_key': settings.STACKEXCHANGE_CLIENT_KEY, 'access_token': cred.auth_secret})
                if resp.status_code == 200:
                    data = resp.json()
                    for site in data['items']:
                        url = urlparse(site['site_url'])
                        if url.netloc == source.auth_id:
                            source.server = 'https://'+url.netloc
                            source.name = site['site_name']
                            break

                source.save()
                return redirect('channels', community_id=view.community.id, source_id=source.id)

        site_choices = []
        resp = requests.get(API_BASE_PATH + SELF_SITES_URL % {'access_key': settings.STACKEXCHANGE_CLIENT_KEY, 'access_token': cred.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            for site in data['items']:
                url = urlparse(site['site_url'])
                site_choices.append((url.netloc, site['site_name']))
        else:
            messages.error(request, "Failed to retrieve Stack Exchange sites: %s"%  resp.content)

        site_choices.append(("other", "other..."))
        form = StackExchangeSiteForm(instance=new_source)
        form.fields['auth_id'].widget.choices = site_choices
        context = view.context
        context.update({
            "source_form": form,
            'source_plugin': 'StackExchange',
            'submit_text': 'Add',
            'submit_class': 'btn btn-success',
        })
        return render(request, "savannahv2/source_add.html", context)

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    if not community.management.can_add_source():
        messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
        return redirect('sources', community_id=community.id)
    client_id = settings.STACKEXCHANGE_CLIENT_ID
    stackexchange_auth_scope = [
        'no_expiry',
        'private_info',
    ]
    callback_uri = request.build_absolute_uri(reverse('stackexchange_callback'))
    client = OAuth2Session(client_id, scope=stackexchange_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)
    url = urlparse(authorization_url)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    request.session['oauth_stackexchange_instance'] = url.scheme + '://' + url.netloc
    return redirect(authorization_url)


def callback(request):
    client_id = settings.STACKEXCHANGE_CLIENT_ID
    client_secret = settings.STACKEXCHANGE_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('stackexchange_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), include_client_id=client_id, client_secret=client_secret)
        print(token)
        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, connector="corm.plugins.stackexchange", server=request.session['oauth_stackexchange_instance'], defaults={"auth_id":  None, "auth_secret": token['access_token']})
        
        return redirect('stackexchange_add')
    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect to your Stackexchange account: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('add', SourceAdd.as_view, name='stackexchange_add'),
    path('auth', authenticate, name='stackexchange_auth'),
    path('callback', callback, name='stackexchange_callback'),
]

class StackExchangePlugin(BasePlugin):

    def get_add_view(self):
        return SourceAdd.as_view

    def get_identity_url(self, contact):
        if contact.origin_id:
            stackexchange_id = contact.origin_id.split("/")[-1]
            return "https://%s/users/%s" % (contact.source.auth_id, stackexchange_id)
        else:
            return None

    def get_icon_name(self):
        return 'fab fa-stack-overflow'

    def get_add_view(self):
        return SourceAdd.as_view

    def get_source_type_name(self):
        return "Stack Exchange"

    def get_import_command_name(self):
        return "stackexchange"

    def get_source_importer(self, source):
        return StackExchangeImporter(source)

    def search_channels(self, source, text):
        channels = []
        # popular tags
        resp = requests.get(API_BASE_PATH + SITE_SEARCH_TAGS_URL % {'search': text, 'site': source.auth_id, 'access_key': settings.STACKEXCHANGE_CLIENT_KEY, 'access_token': source.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            for channel in data['items']:
                channels.append(
                    {
                        'id': channel['name'],
                        'name': channel['name'],
                        'topic': '',
                        'count':channel['count'],
                        'is_private': channel['is_moderator_only'],
                    }
                )
                if len(channels) >= 100:
                    break       
        return channels

    def get_channels(self, source):
        channel_ids = set()
        channels = []
        # User's tags
        resp = requests.get(API_BASE_PATH + SITE_TAGS_URL % {'site': source.auth_id, 'access_key': settings.STACKEXCHANGE_CLIENT_KEY, 'access_token': source.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            for channel in data['items']:
                channels.append(
                    {
                        'id': channel['name'],
                        'name': channel['name'],
                        'topic': '',
                        'count':channel['count'] * 1000000000, # To put these at the top of the channels list
                        'is_private': channel['is_moderator_only'],
                    }
                )
                channel_ids.add(channel['name'])

        # popular tags
        resp = requests.get(API_BASE_PATH + SITE_ALL_TAGS_URL % {'site': source.auth_id, 'access_key': settings.STACKEXCHANGE_CLIENT_KEY, 'access_token': source.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            for channel in data['items']:
                if channel['name'] in channel_ids:
                    continue
                channels.append(
                    {
                        'id': channel['name'],
                        'name': channel['name'],
                        'topic': '',
                        'count':channel['count'],
                        'is_private': channel['is_moderator_only'],
                    }
                )
                channel_ids.add(channel['name'])
                if len(channel_ids) >= 100:
                    break
        return channels

class StackExchangeImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(source)
        self.TIMESTAMP_FORMAT = '%s'
        self.ANSWER_CONTRIBUTION, created = ContributionType.objects.get_or_create(community=source.community, source=source, name="Support")

    def strftime(self, dtime):
        return int(dtime.timestamp())

    def strptime(self, dtimestamp):
        return datetime.datetime.fromtimestamp(dtimestamp)

    def api_call(self, path):
        full_path = API_BASE_PATH + path
        auth_params = {
            'site': self.source.auth_id,
            'key': settings.STACKEXCHANGE_CLIENT_KEY,
            'access_token': self.source.auth_secret,
        }
        full_path += '&'+urlencode(auth_params)
        return self.api_request(full_path, headers=[])

    def import_channel(self, channel, from_date, full_import=False):
        source = channel.source
        community = source.community
        
        questions = set()
        questions_page = 1
        while questions_page:
            # Pause between pages when doing a full import
            if full_import and questions_page > 1:
                sleep(5)

            question_resp = self.api_call(SITE_QUESTIONS_URL % {
                'tag': channel.origin_id,
                'page': questions_page,
                'from_date': self.strftime(from_date),
            })
            if question_resp.status_code == 200:
                question_data = question_resp.json()
                for question in question_data.get('items'):
                    #print(question)
                    tstamp = self.strptime(question.get('creation_date'))
                    convo_link = question.get('link')
                    se_user = question.get('owner')
                    se_user_id = se_user.get('link')
                    if se_user_id is None:
                        se_user_id = se_user.get('display_name')
                        se_username = se_user.get('display_name')
                    else:
                        se_username = se_user_id.split('/')[-1]

                    speaker = self.make_member(origin_id=se_user.get('user_id'), detail=se_username, name=se_user['display_name'], tstamp=tstamp, channel=channel, speaker=True, avatar_url=se_user.get('profile_image'))
                    question_text = re.sub('<[^<]+?>', '', question.get('body'))
                    convo = self.make_conversation(origin_id=question.get('question_id'), channel=channel, speaker=speaker, content=question_text, tstamp=tstamp, location=convo_link, thread=None, dedup=True)
                    convo.title = question.get('title')

                    questions.add(convo)

                if question_data.get('has_more', False):
                    questions_page += 1
                else:
                    questions_page = 0
                    break

            # Questions api call failed
            else:
                print("Question lookup failed: %s" % question_resp.content)


        answers = set()
        for question_convo in questions:
            answers_page = 1
            while answers_page:
                # Pause between pages when doing a full import
                if full_import and answers_page > 1:
                    sleep(5)

                answer_resp = self.api_call(SITE_ANSWERS_URL % {
                    'question_id': question_convo.origin_id,
                    'page': answers_page,
                    'from_date': self.strftime(from_date),
                })
                if answer_resp.status_code == 200:
                    answer_data = answer_resp.json()
                    for answer in answer_data.get('items'):
                        #print(answer)
                        tstamp = self.strptime(answer.get('creation_date'))
                        convo_link = answer.get('link')
                        se_user = answer.get('owner')
                        se_user_id = se_user.get('link')
                        if se_user_id is None:
                            se_user_id = se_user.get('display_name')
                            se_username = se_user.get('display_name')
                        else:
                            se_username = se_user_id.split('/')[-1]

                        answer_link = question_convo.location+'#%s'%answer.get('answer_id')
                        speaker = self.make_member(origin_id=se_user.get('user_id'), detail=se_username, name=se_user['display_name'], tstamp=tstamp, channel=channel, speaker=True, avatar_url=se_user.get('profile_image'))

                        answer_text = re.sub('<[^<]+?>', '', answer.get('body'))
                        answer_convo = self.make_conversation(origin_id=answer.get('answer_id'), channel=channel, speaker=speaker, content=answer_text, tstamp=tstamp, location=answer_link, thread=question_convo, dedup=True)
                        self.make_participant(answer_convo, speaker)
                        self.make_participant(answer_convo, question_convo.speaker)
                        self.make_participant(question_convo, speaker)

                        answers.add(answer_convo)
                        if answer.get('is_accepted'):
                            #print(answer)
                            title = "Answered: %s" % question_convo.title
                            contrib, created = Contribution.objects.update_or_create(origin_id=answer.get('answer_id'), community=self.community, defaults={'contribution_type':self.ANSWER_CONTRIBUTION, 'channel':channel, 'author':speaker, 'timestamp':tstamp, 'title':title, 'location':answer_link})
                            # Not all comments should get the channel tag, but all PRs should
                            if channel.tag:
                                contrib.tags.add(channel.tag)
                                answer_convo.tags.add(channel.tag)
                            # Make contrib
                            answer_convo.contribution = contrib
                            answer_convo.save()
                            pass

                    if answer_data.get('has_more', False):
                        answers_page += 1
                    else:
                        answers_page = 0
                        break

                # Answers api call failed
                else:
                    print("Answer lookup failed: %s" % answer_resp.content)

        posts = questions.union(answers)
        for post in posts:
            posts_page = 1
            while posts_page:
                # Pause between pages when doing a full import
                if full_import and posts_page > 1:
                    sleep(5)

                comments_resp = self.api_call(SITE_COMMENTS_URL % {
                    'question_id': post.origin_id,
                    'page': posts_page,
                    'from_date': self.strftime(from_date),
                })
                if comments_resp.status_code == 200:
                    comments_data = comments_resp.json()
                    for comment in comments_data.get('items'):
                        #print(comment)
                        tstamp = self.strptime(comment.get('creation_date'))
                        convo_link = comment.get('link')
                        se_user = comment.get('owner')
                        se_user_id = se_user.get('link')
                        if se_user_id is None:
                            se_user_id = se_user.get('display_name')
                            se_username = se_user.get('display_name')
                        else:
                            se_username = se_user_id.split('/')[-1]

                        comment_link = post.location+'#comment%s_%s' % (comment.get('comment_id'), post.origin_id)
                        speaker = self.make_member(origin_id=se_user.get('user_id'), detail=se_username, name=se_user['display_name'], tstamp=tstamp, channel=channel, speaker=True, avatar_url=se_user.get('profile_image'))

                        comment_text = re.sub('<[^<]+?>', '', comment.get('body'))
                        comment_convo = self.make_conversation(origin_id=comment.get('comment_id'), channel=channel, speaker=speaker, content=comment_text, tstamp=tstamp, location=comment_link, thread=post, dedup=True)
                        self.make_participant(comment_convo, speaker)
                        self.make_participant(comment_convo, post.speaker)
                        self.make_participant(post, speaker)


                    if comments_data.get('has_more', False):
                        comment_page += 1
                    else:
                        comment_page = 0
                        break

                # Comments api call failed
                else:
                    print("Comments lookup failed: %s" % comments_resp.content)

    