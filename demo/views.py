import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import forms
from django.contrib.auth.models import User
from django.conf import settings

from corm.models import *
from demo.models import Demonstration

# Create your views here.
class NewCommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ['name', 'logo']

@login_required
def new_demo(request):
    community_count = Demonstration.objects.filter(status=Demonstration.IN_USE, community__owner=request.user).count()
    if community_count >= 2:
        messages.warning(request, "Sorry, but you may not have more than 2 demonstration communities at a time.")
        return redirect('home')

    try:
        demo = Demonstration.objects.filter(status=Demonstration.READY).order_by('created')[0]
        demo.community.name = None
        demo.community.logo = None
        demo.community.owner = request.user
        community = demo.community
    except:
        if request.method == "POST":
            return redirect('demo:new')
        else:
            messages.error(request, "Sorry, but we've temporarily run out of available demos, please give us a few minutes to create more.")
            community = Community(owner=request.user)
    if request.method == "POST":
        form = NewCommunityForm(request.POST, files=request.FILES, instance=demo.community)
        if form.is_valid():
            new_community = form.save()
            if new_community.managers is None:
                new_community.managers = Group.objects.create(name="%s Managers (%s)" % (new_community.name, new_community.id))
                new_community.owner.groups.add(new_community.managers)
                new_community.save()
            staff_domain = new_community.name.replace(" ", "").lower() + ".com"
            new_community.company_set.filter(is_staff=True).update(name=new_community.name, website="https://%s" % staff_domain, icon_url=settings.SITE_ROOT+new_community.icon.url)
            CompanyDomains.objects.filter(company__is_staff=True).update(domain=staff_domain)

            system_user = User.objects.get(username=settings.SYSTEM_USER)
            MemberWatch.objects.filter(member__community=new_community, manager=system_user).update(manager=request.user)
            Task.objects.filter(community=new_community, owner=system_user).update(owner=request.user)
            new_profile, created = ManagerProfile.objects.get_or_create(community=community, user=request.user)
            try:
                prev_profile = ManagerProfile.objects.get(community=community, user=system_user)
                new_profile.member = prev_profile.member
                new_profile.save()
            except:
                # No manager profile for previous owner
                pass

            demo.expires = datetime.datetime.utcnow() + datetime.timedelta(hours=settings.DEMO_DURATION_HOURS)
            demo.status = demo.IN_USE
            demo.save()

            # Redirect to company creation form
            messages.success(request, "Welcome to your Savannah CRM demonstration community. We have generated some example data for you to see what Savannah CRM can do.")
            messages.warning(request, "Your demo will be available for %s hours." % settings.DEMO_DURATION_HOURS)
            return redirect('dashboard', community_id=new_community.id)
    else:
        form = NewCommunityForm(instance=community)

    context = {
        "form": form,
    }    
    return render(request, 'demo/community_add.html', context)