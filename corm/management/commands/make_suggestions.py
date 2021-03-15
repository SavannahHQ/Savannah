# dups = Contact.objects.filter(source__community_id=1).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by().filter(dup_count__gt=1)

from django.core.management.base import BaseCommand, CommandError
import os
import sys
import datetime
import operator

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.feature_extraction import text 

from django.db.models import Count
from django.shortcuts import reverse
from corm.models import Community, Member, Conversation, Tag, Contact, Source, ContributionType, Project, MemberLevel
from corm.models import SuggestTag, SuggestMemberMerge, SuggestMemberTag, SuggestConversationTag, SuggestConversationAsContribution, SuggestTask
from corm.models import pluralize
from notifications.signals import notify

class Command(BaseCommand):
    help = 'Create suggested maintenance actions'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)

    def handle(self, *args, **options):
        community_id = options.get('community_id')
        self.verbosity = options.get('verbosity')

        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            communities = [community]
        else:
            communities = Community.objects.all()

        for community in communities:
            if community.suggest_merge:
                self.make_merge_suggestions(community)
            if community.suggest_contribution:
                self.make_conversation_helped_suggestions(community)
            if community.suggest_tag:
                self.make_tag_suggestions(community)
            if community.suggest_task:
                self.make_followup_suggestions(community)

    def make_merge_suggestions(self, community):
        merge_count = 0
        # Check for duplicate usernames
        dups = Contact.objects.filter(member__community=community, email_address__isnull=False).values('email_address').annotate(dup_count=Count('member_id', distinct=True)).order_by('email_address').filter(dup_count__gt=1)
        print("Found %s duplicate email addresses" % len(dups))
        i = 0
        for dup in dups:
            if dup['dup_count'] > 1:
                if self.verbosity >= 3:
                    print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, contact__email_address=dup['email_address']).order_by('id').distinct()
                destination_member = members[0]
                if self.verbosity >= 3:
                    print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    if self.verbosity >= 3:
                        print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.get_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Email match: %s' % dup['email_address']})
                    if created:
                        merge_count += 1

        # Check for duplicate usernames
        dups = Contact.objects.filter(member__community=community).values('detail').annotate(dup_count=Count('member_id', distinct=True)).order_by('detail').filter(dup_count__gt=1)
        print("Found %s duplicate usernames" % len(dups))
        i = 0
        for dup in dups:
            if dup['dup_count'] > 1:
                if self.verbosity >= 3:
                    print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, contact__detail=dup['detail']).order_by('id').distinct()
                destination_member = members[0]
                if self.verbosity >= 3:
                    print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    if self.verbosity >= 3:
                        print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.get_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Username match: %s' % dup['detail']})
                    if created:
                        merge_count += 1

        # Check for duplicate display names
        dups = Member.objects.filter(community=community).values('name').annotate(dup_count=Count('id', distinct=True)).order_by('name').filter(dup_count__gt=1)
        print("Found %s duplicate names" % len(dups))
        i = 0
        for dup in dups:
            names = dup['name'].split(' ')
            if dup['dup_count'] > 1 and len(names) > 1:
                if self.verbosity >= 3:
                    print("%s: %s" % (i, dup))
                i += 1
                members = Member.objects.filter(community=community, name=dup['name']).order_by('id').distinct()
                destination_member = members[0]
                if self.verbosity >= 3:
                    print("Target member: [%s] %s" % (destination_member.id, destination_member))
                for source_member in members[1:]:
                    if self.verbosity >= 3:
                        print("    <- [%s] %s" % (source_member.id, source_member))
                    suggestion, created = SuggestMemberMerge.objects.get_or_create(community=community, destination_member=destination_member, source_member=source_member, defaults={'reason':'Full name match: %s' % dup['name']})
                    if created:
                        merge_count += 1

        # Notify managers of new suggestions
        print("Suggested %s member merges" % merge_count)
        if merge_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                recipient=recipients, 
                verb="has %s new merge %s" % (merge_count, pluralize(merge_count, "suggestion")),
                level='info',
                icon_name="fas fa-people-arrows",
                link=reverse('member_merge_suggestions', kwargs={'community_id':community.id})
            )

    def make_conversation_helped_suggestions(self, community):
        suggestion_count = 0
        try:
            thankful = Tag.objects.get(community=community, name="thankful")
        except:
            print("%s has no #thankful tag" % community)
            return

        # Only look at thankful converstions
        convos = Conversation.objects.filter(speaker__community=community, tags=thankful, contribution=None, contribution_suggestions=None)

        # Exclude greetings as they are usually the start of a conversation
        try:
            greeting = Tag.objects.get(community=community, name="greeting")
            convos = convos.exclude(tags=greeting)
        except:
            print("%s has no #greeting tag" % community)

        # From Chat-style sources
        chat_sources = Source.objects.filter(community=community, connector__in=('corm.plugins.slack', 'corm.plugins.discord', 'corm.plugins.reddit'))
        convos = convos.filter(channel__source__in=chat_sources)

        # Involving only the speaker and one other participant
        convos = convos.annotate(participant_count=Count('participation')).filter(participant_count=2)
        convos = convos.select_related('channel').order_by('channel', '-timestamp')

        print("%s potential support contributions in %s" % (convos.count(), community))
        positive_words = ('!', ':)', 'smile', 'smiling', 'fixed', 'solved', 'helped', 'worked', 'wasn\'t working', 'answer')
        negative_words = ('?', ':(', 'sad', 'frown', 'broken', 'fail', 'help me', 'helpful', 'error', 'not working', 'isn\t working', 'question', 'please', 'welcome', 'but')
        last_helped = None
        last_channel = None
        for convo in convos:
            if convo.content is None:
                continue
            if last_channel != convo.channel:
                last_helped = None
            last_channel = convo.channel

            # Attempt to see if this was for something helpful
            content = convo.content.lower()
            content_words = content.split(" ")
            score = 0
            if len(content_words) < 20:
                score += 1
            if len(content_words) > 50:
                score -= 1
            for word in positive_words:
                if word in content:
                    score += 1
            for word in negative_words:
                if word in content:
                    score -= 1

            # Support is more likely to be given to community than to staff or bots
            if score >= 1 and convo.speaker.role != Member.COMMUNITY:
                score -= 1

            # Only suggest for high positive scores
            if score < 2:
                continue

            # Exclude conversations that are part of another contribution's thread
            if convo.thread_start:
                if convo.thread_start.contribution:
                    continue

            # Don't count multiple instances in a row helping the same person
            if last_helped == convo.speaker:
                continue
            last_helped = convo.speaker

            helped, created = ContributionType.objects.get_or_create(
                community=community,
                source_id=convo.channel.source_id,
                name="Support",
            )
            supporter = convo.participation.exclude(member_id=convo.speaker.id)[0]
            suggestion, created = SuggestConversationAsContribution.objects.get_or_create(
                community=community,
                reason="%s gave support to %s" % (supporter.member, convo.speaker),
                conversation=convo,
                contribution_type=helped,
                source_id=convo.channel.source_id,
                score=score,
                title="Helped %s in %s" % (convo.speaker, convo.channel),
            )
            if created:
                suggestion_count += 1

        print("Suggested %s contributions" % suggestion_count)
        if suggestion_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                recipient=recipients, 
                verb="has %s new contribution %s" % (suggestion_count, pluralize(suggestion_count, "suggestion")),
                level='info',
                icon_name="fas fa-shield-alt",
                link=reverse('conversation_as_contribution_suggestions', kwargs={'community_id':community.id})
            )

    # Tag Suggestions
    def sort_coo(self, coo_matrix):
        tuples = zip(coo_matrix.col, coo_matrix.data)
        return sorted(tuples, key=lambda x: (x[1], x[0]), reverse=True)

    def extract_topn_from_vector(self, feature_names, sorted_items, topn=10):
        """get the feature names and tf-idf score of top n items"""
        
        #use only topn items from vector
        sorted_items = sorted_items[:topn]

        score_vals = []
        feature_vals = []
        
        # word index and corresponding tf-idf score
        for idx, score in sorted_items:
            
            #keep track of feature name and its corresponding score
            score_vals.append(round(score, 3))
            feature_vals.append(feature_names[idx])

        #create a tuples of feature,score
        #results = zip(feature_vals,score_vals)
        results= {}
        for idx in range(len(feature_vals)):
            results[feature_vals[idx]]=score_vals[idx]
        
        return results

    def make_tag_suggestions(self, community):
        print("Calculating tags for %s" % community.name)
        tagged = []
        untagged = []

        conversations = Conversation.objects.filter(channel__source__community=community, content__isnull=False)
        conversations = conversations.filter(timestamp__gte=datetime.datetime.utcnow() - datetime.timedelta(days=60))
        conversations = conversations.exclude(speaker__role=Member.BOT)
        for c in conversations:

            if c.tags.all().count() > 0:
                tagged.append(c.content)
            else:
                untagged.append(c.content)

        used_keywords = set(('http', 'https', 'com', 'github', 'open', 'closed', 'merge', 'pr', 'issue', 'pull', 'issue', 'problem', 'help'))
        # exclude keywords already in tags
        for tag in community.tag_set.filter(keywords__isnull=False):
            for word in tag.keywords.split(","):
                for w in word.split(" "):
                    used_keywords.add(w.lower().strip())
        # exclude usernames
        for ident in Contact.objects.filter(source__community=community):
            used_keywords.add(ident.detail.lower().strip())
        #exclude rejected keywords
        #for s in SuggestTag.objects.filter(community=community, status=SuggestTag.REJECTED):
        #    used_keywords.add(s.keyword)

        stop_words = text.ENGLISH_STOP_WORDS.union(list(used_keywords))

        try:
            cv = CountVectorizer(max_df=0.10,stop_words=stop_words,max_features=10000)
            word_count_vector = cv.fit_transform(tagged)
            transformer = TfidfTransformer(smooth_idf=True,use_idf=True)
            transformer.fit(word_count_vector)
        except ValueError:
            # Not enough content
            return

        feature_names = cv.get_feature_names()

        convo_count = len(untagged)
        tagwords = dict()
        for c in untagged:
            try:
                tf_idf_vector = transformer.transform(cv.transform([c]))
                sorted_items = self.sort_coo(tf_idf_vector.tocoo())
                keywords = self.extract_topn_from_vector(feature_names ,sorted_items, 20)
                for k, v in keywords.items():
                    if len(k) <= 3:
                        continue
                    if k not in tagwords:
                        tagwords[k] = 0
                    tagwords[k] += (v * v)
            except:
                pass
            
        suggestion_count = 0
        if self.verbosity >= 3:
            print("\n===Tag Words===")
        for k, v in sorted(tagwords.items(), key=operator.itemgetter(1), reverse=True):
            percent = 100 * v / convo_count
            if percent >= 0.25:
                if self.verbosity >= 3:
                    print("%s (%0.2f%%)" % (k, percent))
                suggestion, created = SuggestTag.objects.get_or_create(
                    community=community,
                    keyword=k,
                    defaults={
                        'score': 100* percent,
                        'reason': "Frequent keyword found: %s" % k,
                    },
                )
                if created:
                    suggestion_count += 1


        print("Suggested %s tags" % suggestion_count)
        if suggestion_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                recipient=recipients, 
                verb="has %s new tag %s" % (suggestion_count, pluralize(suggestion_count, "suggestion")),
                level='info',
                icon_name="fas fa-tags",
                link=reverse('tag_suggestions', kwargs={'community_id':community.id})
            )

    def make_followup_suggestions(self, community):
        suggestion_count = 0
        for project in Project.objects.filter(community=community):

            members = MemberLevel.objects.filter(community=community, project=project, member__role=Member.COMMUNITY)
            for level in members.filter(level=MemberLevel.CONTRIBUTOR, contribution_count=project.threshold_core-1):
                if self.verbosity >= 3:
                    print("Suggest followup with potential core contributor: %s" % level.member)
                core_followup, created = SuggestTask.objects.get_or_create(
                    community=community,
                    reason='Ready to level-up to core contributor',
                    stakeholder=level.member,
                    project=level.project,
                    created_at=level.timestamp,
                    defaults={
                        'due_in_days':7,
                        'name':'Level-up to Core in %s' % level.project.name,
                        'description': '%s is one contribution away from Core level in %s' % (level.member, level.project.name),
                    },
                )
                if created:
                    suggestion_count += 1
            for level in members.filter(level=MemberLevel.PARTICIPANT, conversation_count__gte=project.threshold_participant * 50):
                if self.verbosity >= 3:
                    print("Suggest followup with potential contributor: %s" % level.member)
                contrib_followup, created = SuggestTask.objects.get_or_create(
                    community=community,
                    reason='Ready to make a contribution',
                    stakeholder=level.member,
                    project=level.project,
                    defaults={
                        'due_in_days':7,
                        'name':'Help make first contribution to %s' % level.project.name,
                        'description':'%s has had %s converesations in %s. Time to help them make a contribution.' % (level.member, level.conversation_count, level.project.name),
                    },
                )
                if created:
                    suggestion_count += 1
        print("Suggested %s tasks" % suggestion_count)
        if suggestion_count > 0:
            recipients = community.managers or community.owner
            notify.send(community, 
                recipient=recipients, 
                verb="has %s new task %s" % (suggestion_count, pluralize(suggestion_count, "suggestion")),
                level='info',
                icon_name="fas fa-tasks",
                link=reverse('task_suggestions', kwargs={'community_id':community.id})
            )
