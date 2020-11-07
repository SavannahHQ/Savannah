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
from frontendv2.views.members import Members, MemberProfile, MemberMerge, AllMembers, MemberAdd, MemberEdit, tag_member, add_note, watch_member, GiftManager
from frontendv2.views.conversations import Conversations
from frontendv2.views.contributions import Contributions, Contributors
from frontendv2.views.connections import Connections
from frontendv2.views.sources import Sources, Channels, tag_channel
from frontendv2.views.tags import Tags, AddTag, EditTag
from frontendv2.views.suggestions import MemberMergeSuggestions, ContributionSuggestions
from frontendv2.views.community import Managers, ManagerPreferences, InviteManager, AcceptManager, resend_invitation, revoke_invitation, Gifts, GiftTypeManager
from frontendv2.views.projects import Projects, ProjectAdd, ProjectOverview, ProjectEdit, ProjectThresholdEdit, ProjectTaskEdit, ProjectTaskAdd
from frontendv2.views.reports import Reports, view_report
from frontendv2 import views

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('community/new', views.new_community, name='add-community'),

    path('dashboard/<int:community_id>/', Dashboard.as_view, name='dashboard'),
    path('members/<int:community_id>/', Members.as_view, name='members'),
    path('members/<int:community_id>/all', AllMembers.as_view, name='all_members'),
    path('member/<int:member_id>/', MemberProfile.as_view, name='member_profile'),
    path('member/<int:community_id>/add', MemberAdd.as_view, name='member_add'),
    path('member/<int:member_id>/edit', MemberEdit.as_view, name='member_edit'),
    path('member/<int:member_id>/merge', MemberMerge.as_view, name='member_merge'),
    path('member/<int:member_id>/tag', tag_member, name='member_tag_form'),
    path('member/<int:member_id>/note', add_note, name='member_note_form'),
    path('member/<int:member_id>/watch', watch_member, name='member_watch_form'),
    path('member/<int:member_id>/gift', GiftManager.add_view, name='gift_add'),
    path('member/<int:member_id>/gift/<int:gift_id>/', GiftManager.edit_view, name='gift_edit'),
    path('conversations/<int:community_id>/', Conversations.as_view, name='conversations'),
    path('contributions/<int:community_id>/', Contributions.as_view, name='contributions'),
    path('contributions/<int:community_id>/contributors', Contributors.as_view, name='contributors'),
    path('contributions/<int:community_id>/contributors.csv', Contributors.as_csv, name='contributors_csv'),
    path('connections/<int:community_id>/', Connections.as_view, name='connections'),
    path('connections/<int:community_id>/json', Connections.as_json, name='connections_json'),
    path('suggest/<int:community_id>/merge', MemberMergeSuggestions.as_view, name='member_merge_suggestions'),
    path('suggest/<int:community_id>/contributions', ContributionSuggestions.as_view, name='conversation_as_contribution_suggestions'),

    path('reports/<int:community_id>/', Reports.as_view, name='reports'),
    path('reports/<int:community_id>/view/<int:report_id>/', view_report, name='report_view'),

    path('projects/<int:community_id>/', Projects.as_view, name='projects'),
    path('projects/<int:community_id>/add', ProjectAdd.as_view, name='project_add'),
    path('projects/<int:community_id>/overview/<int:project_id>/', ProjectOverview.as_view, name='project_overview'),
    path('projects/<int:community_id>/overview/<int:project_id>/edit', ProjectEdit.as_view, name='project_edit'),
    path('projects/<int:community_id>/overview/<int:project_id>/thresholds', ProjectThresholdEdit.as_view, name='project_threshold_edit'),
    path('projects/<int:community_id>/overview/<int:project_id>/task/add', ProjectTaskAdd.as_view, name='project_task_add'),
    path('projects/<int:community_id>/overview/<int:project_id>/task/<int:task_id>/', ProjectTaskEdit.as_view, name='project_task_edit'),
    path('projects/<int:community_id>/overview/<int:project_id>/task/done', ProjectOverview.mark_task_done, name='project_task_done'),
    path('gifts/<int:community_id>/', Gifts.as_view, name='gifts'),
    path('gifts/<int:community_id>/add', GiftTypeManager.add_view, name='gift_type_add'),
    path('gifts/<int:community_id>/edit/<int:type_id>/', GiftTypeManager.edit_view, name='gift_type_edit'),
    path('managers/<int:community_id>/', Managers.as_view, name='managers'),
    path('managers/<int:community_id>/invite', InviteManager.as_view, name='manager_invite'),
    path('managers/<int:community_id>/accept', AcceptManager.as_view, name='manager_accept'),
    path('managers/<int:community_id>/resend/', resend_invitation, name='resend_invite'),
    path('managers/<int:community_id>/revoke/', revoke_invitation, name='revoke_invite'),
    path('managers/<int:community_id>/preferences', ManagerPreferences.as_view, name='manager_preferences'),
    path('sources/<int:community_id>/', Sources.as_view, name='sources'),
    path('sources/<int:community_id>/json', Sources.as_json, name='members_json'),
    path('sources/<int:community_id>/channels/<int:source_id>/', Channels.as_view, name='channels'),
    path('sources/<int:community_id>/channels/<int:source_id>/tag', tag_channel, name='channel_tag_form'),
    path('tags/<int:community_id>/', Tags.as_view, name='tags'),
    path('tags/<int:community_id>/add', AddTag.as_view, name='tag_add'),
    path('tag/<int:tag_id>/edit', EditTag.as_view, name='tag_edit'),
]
