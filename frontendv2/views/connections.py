import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Count, Max
from django.utils.safestring import mark_safe
from django.http import JsonResponse

from corm.models import *

class Connections:
    def __init__(self, community_id, tag=None, member_tag=None):
        self.community = get_object_or_404(Community, id=community_id)
        self._connectionsChart = None
        if tag:
            self.tag = get_object_or_404(Tag, name=tag)
        else:
            self.tag = None



@login_required
def connections(request, community_id):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all()))
    request.session['community'] = community_id
    kwargs = dict()
    if 'tag' in request.GET:
        kwargs['tag'] = request.GET.get('tag')


    connections = Connections(community_id, **kwargs)
    try:
        user_member = Member.objects.get(user=request.user, community=conversations.community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "active_community": connections.community,
        "active_tab": "conversations",
        "view": connections,
    }
    return render(request, 'savannahv2/connections.html', context)

@login_required
def connections_json(request, community_id):
    community = get_object_or_404(Community, id=community_id)
    nodes = list()
    links = list()
    member_map = dict()
    member_ids = set()
    connected = set()

    connections = MemberConnection.objects.filter(from_member__community=community, last_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))
    if 'tag' in request.GET:
        tag = get_object_or_404(Tag, community=community, name=request.GET.get("tag"))
        connections = connections.filter(Q(to_member__tags=tag)|Q(from_member__tags=tag))
    connections = connections.annotate(from_member_name=F('from_member__name'), to_member_name=F('to_member__name'))

    for connection in connections:
        if connection.from_member_id != connection.to_member_id:
            if not (connection.to_member_id, connection.from_member_id) in connected: 
                links.append({"source":connection.from_member_id, "target":connection.to_member_id})
                connected.add((connection.from_member_id, connection.to_member_id))
                member_map[connection.from_member_id] = connection.from_member_name
                member_map[connection.to_member_id] = connection.to_member_name

    for member_id, member_name in member_map.items():
        nodes.append({"id":member_id, "name":member_name})
                
    return JsonResponse({"nodes":nodes, "links":links})
