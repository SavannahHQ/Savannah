import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max

from corm.models import *

class Members:
    def __init__(self, community_id, tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._membersChart = None
        self._tagsChart = None
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
            activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return most_active[:10]

    @property
    def most_connected(self):
        if self.tag:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30), connections__tags=self.tag)))
        else:
            members = Member.objects.filter(community=self.community).annotate(connection_count=Count('connections', filter=Q(memberconnection__last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))))

        connection_counts = dict()
        for m in members:
            connection_counts[m] = m.connection_count
        most_connected = [(member, count) for member, count in sorted(connection_counts.items(), key=operator.itemgetter(1))]
        most_connected.reverse()
        return most_connected[:10]

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
                month = m.date_added.month
                if month not in months:
                    months.append(month)
                counts[month] = total
            self._membersChart = (months, counts)
        return self._membersChart
        
    @property
    def members_chart_months(self):
        (months, counts) = self.getMembersChart()
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return [names[month-1] for month in months[-12:]]

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


@login_required
def members(request, community_id):
    communities = Community.objects.filter(owner=request.user)
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
            members = members.filter(name__icontains=self.search)

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
    communities = Community.objects.filter(owner=request.user)
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
