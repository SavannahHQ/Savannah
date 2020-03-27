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
    try:
        user_member = Member.objects.get(user=request.user, community=community)
    except:
        user_member = None
    context = {
        "communities": communities,
        "community": community,
        "user_member": user_member,
    }
    return render(request, 'savannah/dashboard.html', context)
