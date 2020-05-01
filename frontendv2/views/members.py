import operator
from functools import reduce
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max

from corm.models import *

class Members:
    def __init__(self, community_id, tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._tagsChart = None
        self._sourcesChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None
    
    @property
    def all_members(self):
        if self.tag:
            members = Member.objects.filter(community=self.community, tags=self.tag).annotate(note_count=Count('note'), tag_count=Count('tags'))
        else:
            members = Member.objects.filter(community=self.community).annotate(note_count=Count('note'), tag_count=Count('tags'))
        return members

    @property
    def new_members(self):
        if self.tag:
            members = Member.objects.filter(community=self.community, tags=self.tag)
        else:
            members = Member.objects.filter(community=self.community)
        return members.order_by("-date_added")[:10]

    @property
    def recently_active(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(last_active=Max('conversation__timestamp', filter=Q(conversation__timestamp__isnull=False, conversation__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(last_active=Max('conversation__timestamp', filter=Q(conversation__timestamp__isnull=False)))
        actives = dict()
        for m in members:
            if m.last_active is not None:
                actives[m] = m.last_active
        recently_active = [(member, tstamp) for member, tstamp in sorted(actives.items(), key=operator.itemgetter(1), reverse=True)]
        
        return recently_active[:10]

    @property
    def most_active(self):
        activity_counts = dict()
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30), conversation__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))))
        for m in members:
            if m.conversation_count > 0:
                activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:20]

    @property
    def most_connected(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30), connections__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))))

        connection_counts = dict()
        for m in members:
            if m.connection_count > 0:
                connection_counts[m] = m.connection_count
        most_connected = [(member, count) for member, count in sorted(connection_counts.items(), key=operator.itemgetter(1))]
        most_connected.reverse()
        return most_connected[:20]

    def getMembersChart(self):
        if not self._membersChart:
            months = list()
            counts = dict()
            total = 0
            if self.tag:
                members = Member.objects.filter(community=self.community, tags=self.tag).order_by("date_added")
            else:
                members = Member.objects.filter(community=self.community).order_by("date_added")
            for m in members:
                total += 1
                month = str(m.date_added)[:7]
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        return [month for month in months[-12:]]

    @property
    def members_chart_counts(self):
        (months, counts) = self.getMembersChart()
        return [counts[month] for month in months[-12:]]

    def getTagsChart(self):
        if not self._tagsChart:
            tags = list()
            counts = dict()
            total = 0
            tags = Tag.objects.filter(community=self.community).annotate(member_count=Count('member')).order_by('-member_count')
            for t in tags:
                counts[t] = t.member_count
            self._tagsChart = [('#'+tag.name, count, '#'+tag.color) for tag, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._tagsChart) > 8:
                other_count = sum([count for tag, count, color in self._tagsChart[7:]])
                self._tagsChart = self._tagsChart[:7]
                self._tagsChart.append(("Other", other_count, "#efefef"))
        return self._tagsChart

    @property
    def tag_names(self):
        chart = self.getTagsChart()
        return [tag[0] for tag in chart]

    @property
    def tag_counts(self):
        chart = self.getTagsChart()
        return [tag[1] for tag in chart]

    @property
    def tag_colors(self):
        chart = self.getTagsChart()
        return [tag[2] for tag in chart]

    def getSourcesChart(self):
        if not self._sourcesChart:
            counts = dict()
            other_count = 0
            sources = Source.objects.filter(community=self.community).annotate(identity_count=Count('contact'))
            for source in sources:
                if source.identity_count > 5:
                    counts[source.name] = source.identity_count
                else:
                    other_count += source.identity_count
            self._sourcesChart = [(source, count) for source, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._sourcesChart) > 8:
                other_count += sum([count for tag, count in self._sourcesChart[7:]])
            if other_count > 0:
                self._sourcesChart = self._sourcesChart[:7]
                self._sourcesChart.append(("Other", other_count, "#efefef"))
        return self._sourcesChart

    @property
    def source_names(self):
        chart = self.getSourcesChart()
        return [source[0] for source in chart]

    @property
    def source_counts(self):
        chart = self.getSourcesChart()
        return [source[1] for source in chart]

@login_required
def members(request, community_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))
    request.session['community'] = community_id
    if 'tag' in request.GET:
        members = Members(community_id, tag=request.GET.get('tag'))
    else:
        members = Members(community_id)

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": members.community,
        "active_tab": "members",
        "view": members,
    }
    return render(request, 'savannahv2/members.html', context)

class AllMembers:
    def __init__(self, community_id, page=1, search=None, tag=None):
        self.RESULTS_PER_PAGE = 100
        self.community = get_object_or_404(Community, id=community_id)
        try:
            self.page = int(page)
        except:
            self.page = 1

        if search:
            self.search = search.lower()
        else:
            self.search = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None
        self.result_count = 0
    
    @property
    def all_members(self):
        members = Member.objects.filter(community=self.community).annotate(note_count=Count('note'), tag_count=Count('tags'))
        if self.search:
            members = members.filter(Q(name__icontains=self.search) | Q(contact__detail__icontains=self.search))

        if self.tag:
            members = members.filter(tags=self.tag)

        members = members.annotate(note_count=Count('note'), tag_count=Count('tags'))
        self.result_count = members.count()
        start = (self.page-1) * self.RESULTS_PER_PAGE
        return members[start:start+self.RESULTS_PER_PAGE]

    @property
    def has_pages(self):
        return self.result_count > self.RESULTS_PER_PAGE

    @property
    def last_page(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return pages+1

    @property
    def page_links(self):
        pages = int(self.result_count / self.RESULTS_PER_PAGE)
        return [page+1 for page in range(pages+1)]

@login_required
def all_members(request, community_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))
    request.session['community'] = community_id

    view = AllMembers(community_id, page=request.GET.get('page', 1), search=request.GET.get('search', None), tag=request.GET.get('tag', None))

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": view.community,
        "active_tab": "members",
        "view": view,
    }
    return render(request, 'savannahv2/all_members.html', context)

class MemberProfile:
    def __init__(self, member_id, page=1, tag=None):
        self.RESULTS_PER_PAGE = 100
        self.member = get_object_or_404(Member, id=member_id)
        self._engagementChart = None
        self._channelsChart = None
        try:
            self.page = int(page)
        except:
            self.page = 1
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None

    @property
    def all_conversations(self):
        if self.tag:
            conversations = Conversation.objects.filter(channel__source__community=self.member.community, participants=self.member, tags=self.tag).annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        else:
            conversations = Conversation.objects.filter(channel__source__community=self.member.community, participants=self.member).annotate(tag_count=Count('tags'), channel_name=F('channel__name'), channel_icon=F('channel__source__icon_name')).order_by('-timestamp')
        return conversations[:20]

    def getEngagementChart(self):
        if not self._engagementChart:
            conversations_counts = dict()
            activity_counts = dict()

            if self.tag:
                conversations = Conversation.objects.filter(channel__source__community=self.member.community, participants=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90), tags=self.tag).order_by("timestamp")
            else:
                conversations = Conversation.objects.filter(channel__source__community=self.member.community, participants=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90)).order_by("timestamp")
            for c in conversations:
                month = str(c.timestamp)[:10]
                if month not in conversations_counts:
                    conversations_counts[month] = 1
                else:
                    conversations_counts[month] += 1

            if self.tag:
                activity = Contribution.objects.filter(community=self.member.community, author=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90), tags=self.tag).order_by("timestamp")
            else:
                activity = Contribution.objects.filter(community=self.member.community, author=self.member, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=90)).order_by("timestamp")
            for a in activity:
                month = str(a.timestamp)[:10]
                if month not in activity_counts:
                    activity_counts[month] = 1
                else:
                    activity_counts[month] += 1
            self._engagementChart = (conversations_counts, activity_counts)
        return self._engagementChart
        
    @property
    def engagement_chart_months(self):
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [str(day)[:10] for day in date_list]

    @property
    def engagement_chart_conversations(self):
        (conversations_counts, activity_counts) = self.getEngagementChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [conversations_counts.get(str(day)[:10], 0) for day in date_list]

    @property
    def engagement_chart_activities(self):
        (conversations_counts, activity_counts) = self.getEngagementChart()
        base = datetime.datetime.today()
        date_list = [base - datetime.timedelta(days=x) for x in range(90)]
        date_list.reverse()
        return [activity_counts.get(str(day)[:10], 0) for day in date_list]

    def getChannelsChart(self):
        channel_names = dict()
        if not self._channelsChart:
            channels = list()
            counts = dict()
            total = 0
            if self.tag:
                channels = Channel.objects.filter(source__community=self.member.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__participants=self.member, conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180), conversation__tags=self.tag)))
            else:
                channels = Channel.objects.filter(source__community=self.member.community).annotate(conversation_count=Count('conversation', filter=Q(conversation__participants=self.member, conversation__timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=180))))
            for c in channels:
                counts[c.name] = c.conversation_count
            self._channelsChart = [(channel, count) for channel, count in sorted(counts.items(), key=operator.itemgetter(1), reverse=True)]
            if len(self._channelsChart) > 8:
                other_count = sum([count for channel, count in self._channelsChart[7:]])
                self._channelsChart = self._channelsChart[:7]
                self._channelsChart.append(("Other", other_count))
        return self._channelsChart

    @property
    def channel_names(self):
        chart = self.getChannelsChart()
        return [channel[0] for channel in chart]

    @property
    def channel_counts(self):
        chart = self.getChannelsChart()
        return [channel[1] for channel in chart]

def member_profile(request, member_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))

    view = MemberProfile(member_id, page=request.GET.get('page', 1), tag=request.GET.get('tag', None))
    request.session['community'] = view.member.community.id

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": view.member.community,
        "active_tab": "members",
        "view": view,
    }
    return render(request, 'savannahv2/member_profile.html', context)

class MemberMerge:
    def __init__(self, member_id, search=None, page=1):
        self.RESULTS_PER_PAGE = 100
        self.member = get_object_or_404(Member, id=member_id)
        try:
            self.page = int(page)
        except:
            self.page = 1
        if search:
            self.search =search
        else:
            self.search = None

    @property
    def possible_matches(self):
        matches = Member.objects.filter(community=self.member.community)
        if self.search:
            return matches.filter(Q(name__icontains=self.search)|Q(contact__detail__icontains=self.search))
        else:
            same_contact = [contact.detail for contact in self.member.contact_set.all()]
            contact_matches = matches.filter(Q(contact__detail__in=same_contact))

            similar_contact = [name for name in self.member.name.split(" ") if len(name) > 2]
            if len(similar_contact) > 1:
                similar_matches = matches.filter(~Q(contact__detail__in=same_contact) & reduce(operator.or_, (Q(contact__detail__icontains=name) for name in similar_contact)))
            elif len(similar_contact) == 1:
                similar_matches = matches.filter(~Q(contact__detail__in=same_contact) & Q(contact__detail__icontains=similar_contact[0]))
            contact_matches = contact_matches.exclude(id=self.member.id).distinct()
            similar_matches = similar_matches.exclude(id=self.member.id).distinct()[:20]
            return list(contact_matches) + list(similar_matches)


def member_merge(request, member_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))

    view = MemberMerge(member_id, search=request.GET.get('search', 0))
    request.session['community'] = view.member.community.id

    if request.method == 'POST':
        merge_with = get_object_or_404(Member, id=request.POST.get('merge_with'))
        view.member.merge_with(merge_with)
        return redirect('member_merge', member_id=member_id)

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": view.member.community,
        "active_tab": "members",
        "view": view,
    }
    return render(request, 'savannahv2/member_merge.html', context)