import operator
import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max

from corm.models import *

from frontendv2.views.dashboard import dashboard
from frontendv2.views.members import members, all_members, member_profile, member_merge
from frontendv2.views.conversations import conversations
from frontendv2.views.contributions import contributions
from frontendv2.views.connections import connections, connections_json

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
