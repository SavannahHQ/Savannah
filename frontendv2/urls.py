"""savannah URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from frontendv2.views.dashboard import Dashboard
from frontendv2.views.members import Members, MemberProfile, MemberMerge, AllMembers, MemberEdit, tag_member
from frontendv2.views.conversations import Conversations
from frontendv2.views.contributions import Contributions
from frontendv2.views.connections import Connections
from frontendv2.views.sources import Sources, Channels, tag_channel
from frontendv2.views.tags import Tags, AddTag, EditTag
from frontendv2.views.suggestions import MemberMergeSuggestions
from frontendv2 import views

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('dashboard/<int:community_id>/', Dashboard.as_view, name='dashboard'),
    path('members/<int:community_id>/', Members.as_view, name='members'),
    path('members/<int:community_id>/all', AllMembers.as_view, name='all_members'),
    path('member/<int:member_id>/', MemberProfile.as_view, name='member_profile'),
    path('member/<int:member_id>/edit', MemberEdit.as_view, name='member_edit'),
    path('member/<int:member_id>/merge', MemberMerge.as_view, name='member_merge'),
    path('member/<int:member_id>/tag', tag_member, name='member_tag_form'),
    path('conversations/<int:community_id>/', Conversations.as_view, name='conversations'),
    path('contributions/<int:community_id>/', Contributions.as_view, name='contributions'),
    path('connections/<int:community_id>/', Connections.as_view, name='connections'),
    path('connections/<int:community_id>/json', Connections.as_json, name='connections_json'),
    path('suggest/<int:community_id>/merge', MemberMergeSuggestions.as_view, name='member_merge_suggestions'),

    path('sources/<int:community_id>/', Sources.as_view, name='sources'),
    path('sources/<int:community_id>/json', Sources.as_json, name='members_json'),
    path('sources/<int:community_id>/channels/<int:source_id>/', Channels.as_view, name='channels'),
    path('sources/<int:community_id>/channels/<int:source_id>//tag', tag_channel, name='channel_tag_form'),
    path('tags/<int:community_id>/', Tags.as_view, name='tags'),
    path('tags/<int:community_id>/add', AddTag.as_view, name='tag_add'),
    path('tag/<int:tag_id>/edit', EditTag.as_view, name='tag_edit'),
]
