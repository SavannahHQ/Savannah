import operator
import datetime
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate, login as login_user, logout as logout_user
from django.contrib import messages

from corm.models import *

# Create your views here.
def index(request):
    sayings = [
        "Herd your cats",
        "Build a better community",
        "Manage your community relationships"
    ]
    return render(request, 'savannahv2/index.html', {'sayings': sayings})

def logout(request):
    if request.user.is_authenticated:
        logout_user(request)
    return redirect(reverse("login") + "?next=%s" % request.GET.get('next'))

def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request=request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login_user(request, user)
                if request.POST.get('next'):
                    return redirect(request.POST.get('next'))

                communities = Community.objects.filter(Q(owner=user) | Q(managers__in=user.groups.all())).order_by('id')
                if len(communities) == 1:
                    return redirect('dashboard', community_id=communities[0].id)
                elif len(communities) > 1:
                    return redirect('home')
                else:
                    # TODO: redirect to community creation screen
                    return redirect('home')
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
            form = AuthenticationForm()

    context = {
        'form': form,
    }
    return render(request, 'savannahv2/login.html', context)

@login_required
def home(request):
    communities = Community.objects.filter(Q(owner=request.user) | Q(managers__in=request.user.groups.all())).order_by('id')
    context = {
        "communities": communities,
    }
    return render(request, 'savannahv2/home.html', context)

class SavannahView:
    def __init__(self, request, community_id):
        request.session['community'] = community_id
        self.request = request
        self.community = get_object_or_404(Community, Q(owner=self.request.user) | Q(managers__in=self.request.user.groups.all()), id=community_id)
        self.active_tab = ""

        try:
            self.user_member = Member.objects.get(user=self.request.user, community=self.community)
        except:
            self.user_member = None

        if 'tag' in request.GET:
            self.tag = get_object_or_404(Tag, community=self.community, name=request.GET.get('tag'))
        else:
            self.tag = None

    @property
    def context(self):
        communities = Community.objects.filter(Q(owner=self.request.user) | Q(managers__in=self.request.user.groups.all()))
        return {
            "communities": communities,
            "active_community": self.community,
            "active_tab": self.active_tab,
            "view": self,
        }
