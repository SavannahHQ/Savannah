import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from corm.models import *

# Create your views here.
def index(request):
    sayings = [
        "Herd your cats",
        "Build a better community",
        "Manage your community relationships"
    ]
    return render(request, 'savannah/index.html', {'sayings': sayings})

@login_required
def home(request):
    communities = Community.objects.filter(owner=request.user)
    context = {
        "communities": communities,
    }
    return render(request, 'savannah/home.html', context)

@login_required
def dashboard(request, community_id):
    communities = Community.objects.filter(owner=request.user)
    community = get_object_or_404(Community, id=community_id)
    request.session['community'] = community_id
    recent_conversations = Conversation.objects.filter(channel__source__community=community, timestamp__gte=datetime.datetime.now() - datetime.timedelta(days=30))
    activity_counts = dict()
    for c in recent_conversations:
        for p in c.participants.all():
            if p in activity_counts:
                activity_counts[p] = activity_counts[p] + 1
            else:
                activity_counts[p] = 1
    most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
    most_active.reverse()

    connections = MemberConnection.objects.filter(from_member__community=community, first_connected__gte=datetime.datetime.now() - datetime.timedelta(days=30))
    connection_counts = dict()
    for c in connections:
            if c.from_member in connection_counts:
                connection_counts[c.from_member] = connection_counts[c.from_member] + 1
            else:
                connection_counts[c.from_member] = 1
    most_connected = [(member, count) for member, count in sorted(connection_counts.items(), key=operator.itemgetter(1))]
    most_connected.reverse()

    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "community": community,
        "user_member": user_member,
        "most_active": most_active[:10],
        "most_connected": most_connected[:10],
    }
    return render(request, 'savannah/dashboard.html', context)
