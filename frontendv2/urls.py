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
from django.contrib.auth import views as auth_views
from django.urls import path

from frontendv2.views.dashboard import Overview, ManagerDashboard, ManagerTaskEdit, ManagerTasksCalendar
from frontendv2.views.members import Members, MemberProfile, MemberActivity, MemberMerge, MemberMergeHistory, AllMembers, MemberAdd, MemberEdit, tag_member, add_note, watch_member, GiftManager, MemberTaskAdd, MemberTaskEdit, followup_on_member, PromoteToContribution
from frontendv2.views.conversations import Conversations
from frontendv2.views.contributions import Contributions, Contributors
from frontendv2.views.connections import Connections
from frontendv2.views.sources import Sources, Channels, tag_channel, add_source
from frontendv2.views.tags import Tags, AddTag, EditTag
from frontendv2.views.suggestions import TagSuggestions, MemberMergeSuggestions, ContributionSuggestions, CompanyCreationSuggestions, TaskSuggestions
from frontendv2.views.community import EditCommunity, Managers, ManagerPreferences, ManagerPasswordChange, ManagerDelete, InviteManager, AcceptManager, resend_invitation, revoke_invitation, Gifts, GiftTypeManager, PublicDashboards
from frontendv2.views.projects import Projects, ProjectsGraph, ProjectAdd, ProjectOverview, ProjectEdit, ProjectThresholdEdit, ProjectTaskEdit, ProjectTaskAdd, ProjectDelete
from frontendv2.views.reports import Reports, view_report
from frontendv2.views.company import Companies, CompanyProfile, AddCompany, EditCompany, tag_company, CompanyLookup, CompanyMerge
from frontendv2.views.events import Events, EventProfile, AddEvent, EditEvent, tag_event, AddAttendee
from frontendv2 import views

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path("account/reset/", views.password_reset_request, name="password_reset"),
    path("account/reset/<request_key>/", views.reset_password, name="reset_password"),

    path('about/brand/', views.branding, name='branding'),

    path('community/new', views.new_community, name='add-community'),

    path('dashboard/<int:community_id>/', ManagerDashboard.as_view, name='dashboard'),
    path('dashboard/<int:community_id>/task/<int:task_id>/', ManagerTaskEdit.as_view, name='manager_task_edit'),
    path('dashboard/<int:community_id>/task/done', ManagerTaskEdit.mark_task_done, name='manager_task_done'),
    path('manager/<str:secret_key>/savannah_tasks.ical', ManagerTasksCalendar(), name='manager_task_ical'),
    path('dashboard/<int:community_id>/gift/received', ManagerDashboard.mark_gift_received, name='manager_gift_received'),
    path('overview/<int:community_id>/', Overview.as_view, name='overview'),
    path('overview/<int:community_id>/publish', Overview.publish, name='publish_overview'),
    path('public/overview/<str:dashboard_id>/', Overview.public, name='public_overview'),
    path('members/<int:community_id>/', Members.as_view, name='members'),
    path('members/<int:community_id>/all', AllMembers.as_view, name='all_members'),
    path('members/<int:community_id>/members.csv', AllMembers.as_csv, name='members_csv'),
    path('member/<int:member_id>/', MemberProfile.as_view, name='member_profile'),
    path('member/<int:member_id>/activity', MemberActivity.as_view, name='member_activity'),
    path('member/<int:member_id>/make_contribution', PromoteToContribution.as_view, name='promote_to_contribution'),
    path('member/<int:community_id>/add', MemberAdd.as_view, name='member_add'),
    path('member/<int:member_id>/edit', MemberEdit.as_view, name='member_edit'),
    path('member/<int:member_id>/merge', MemberMerge.as_view, name='member_merge'),
    path('member/<int:member_id>/merge_history', MemberMergeHistory.as_view, name='merge_history'),
    path('member/<int:member_id>/tag', tag_member, name='member_tag_form'),
    path('member/<int:member_id>/note', add_note, name='member_note_form'),
    path('member/<int:member_id>/watch', watch_member, name='member_watch_form'),
    path('member/<int:member_id>/followup', followup_on_member, name='member_followup_form'),
    path('member/<int:member_id>/gift', GiftManager.add_view, name='gift_add'),
    path('member/<int:member_id>/gift/<int:gift_id>/', GiftManager.edit_view, name='gift_edit'),
    path('member/<int:member_id>/task/add', MemberTaskAdd.as_view, name='task_add'),
    path('member/<int:member_id>/task/<int:task_id>/', MemberTaskEdit.as_view, name='task_edit'),
    path('member/<int:member_id>/task/done', MemberTaskEdit.mark_task_done, name='task_done'),
    path('member/<int:community_id>/publish', Members.publish, name='publish_members'),
    path('public/member/<str:dashboard_id>/', Members.public, name='public_members'),
    path('conversations/<int:community_id>/', Conversations.as_view, name='conversations'),
    path('conversations/<int:community_id>/publish', Conversations.publish, name='publish_conversations'),
    path('public/conversations/<str:dashboard_id>/', Conversations.public, name='public_conversations'),
    path('contributions/<int:community_id>/', Contributions.as_view, name='contributions'),
    path('contributions/<int:community_id>/contributors', Contributors.as_view, name='contributors'),
    path('contributions/<int:community_id>/contributors/publish', Contributors.publish, name='publish_contributors'),
    path('public/contributors/<str:dashboard_id>/', Contributors.public, name='public_contributors'),
    path('contributions/<int:community_id>/contributors.csv', Contributors.as_csv, name='contributors_csv'),
    path('contributions/<int:community_id>/publish', Contributions.publish, name='publish_contributions'),
    path('public/contributions/<str:dashboard_id>/', Contributions.public, name='public_contributions'),
    path('connections/<int:community_id>/', Connections.as_view, name='connections'),
    path('connections/<int:community_id>/json', Connections.as_json, name='connections_json'),
    path('suggest/<int:community_id>/merge', MemberMergeSuggestions.as_view, name='member_merge_suggestions'),
    path('suggest/<int:community_id>/contributions', ContributionSuggestions.as_view, name='conversation_as_contribution_suggestions'),
    path('suggest/<int:community_id>/companies', CompanyCreationSuggestions.as_view, name='company_suggestions'),
    path('suggest/<int:community_id>/tags', TagSuggestions.as_view, name='tag_suggestions'),
    path('suggest/<int:community_id>/tasks', TaskSuggestions.as_view, name='task_suggestions'),

    path('reports/<int:community_id>/', Reports.as_view, name='reports'),
    path('reports/<int:community_id>/view/<int:report_id>/', view_report, name='report_view'),

    path('projects/<int:community_id>/', Projects.as_view, name='projects'),
    path('projects/<int:community_id>/graph', ProjectsGraph.as_view, name='projects_graph'),
    path('projects/<int:community_id>/graph.json', ProjectsGraph.as_json, name='projects_json'),
    path('projects/<int:community_id>/add', ProjectAdd.as_view, name='project_add'),
    path('projects/<int:community_id>/overview/<int:project_id>/', ProjectOverview.as_view, name='project_overview'),
    path('projects/<int:community_id>/delete/<int:project_id>/', ProjectDelete.as_view, name='project_delete'),
    path('projects/<int:community_id>/overview/<int:project_id>/edit', ProjectEdit.as_view, name='project_edit'),
    path('projects/<int:community_id>/overview/<int:project_id>/thresholds', ProjectThresholdEdit.as_view, name='project_threshold_edit'),
    path('projects/<int:community_id>/overview/<int:project_id>/task/add', ProjectTaskAdd.as_view, name='project_task_add'),
    path('projects/<int:community_id>/overview/<int:project_id>/task/<int:task_id>/', ProjectTaskEdit.as_view, name='project_task_edit'),
    path('projects/<int:community_id>/overview/<int:project_id>/task/done', ProjectOverview.mark_task_done, name='project_task_done'),
    path('gifts/<int:community_id>/', Gifts.as_view, name='gifts'),
    path('gifts/<int:community_id>/add', GiftTypeManager.add_view, name='gift_type_add'),
    path('gifts/<int:community_id>/edit/<int:type_id>/', GiftTypeManager.edit_view, name='gift_type_edit'),
    path('community/<int:community_id>/change', EditCommunity.as_view, name='community_edit'),
    path('managers/<int:community_id>/', Managers.as_view, name='managers'),
    path('managers/<int:community_id>/invite', InviteManager.as_view, name='manager_invite'),
    path('managers/<int:community_id>/accept', AcceptManager.as_view, name='manager_accept'),
    path('managers/<int:community_id>/resend/', resend_invitation, name='resend_invite'),
    path('managers/<int:community_id>/revoke/', revoke_invitation, name='revoke_invite'),
    path('managers/<int:community_id>/preferences', ManagerPreferences.as_view, name='manager_preferences'),
    path('managers/<int:community_id>/password', ManagerPasswordChange.as_view, name='manager_password'),
    path('managers/<int:community_id>/delete', ManagerDelete.as_view, name='manager_delete'),
    path('sources/<int:community_id>/', Sources.as_view, name='sources'),
    path('sources/<int:community_id>/add/<str:connector>', add_source, name='add_source'),
    path('sources/<int:community_id>/json', Sources.as_json, name='members_json'),
    path('sources/<int:community_id>/channels/<int:source_id>/', Channels.as_view, name='channels'),
    path('sources/<int:community_id>/channels/<int:source_id>/tag', tag_channel, name='channel_tag_form'),
    path('tags/<int:community_id>/', Tags.as_view, name='tags'),
    path('tags/<int:community_id>/add', AddTag.as_view, name='tag_add'),
    path('tag/<int:tag_id>/edit', EditTag.as_view, name='tag_edit'),
    path('shared/<int:community_id>/', PublicDashboards.as_view, name='public_dashboards'),
    path('companies/<int:community_id>/', Companies.as_view, name='companies'),
    path('companies/<int:community_id>/add', AddCompany.as_view, name='company_add'),
    path('companies/<int:community_id>/tag', tag_company, name='company_tag_form'),
    path('companies/<int:community_id>/lookup', CompanyLookup.as_view, name='company_lookup'),
    path('company/<int:company_id>/', CompanyProfile.as_view, name='company_profile'),
    path('company/<int:company_id>/edit', EditCompany.as_view, name='company_edit'),
    path('company/<int:company_id>/merge', CompanyMerge.as_view, name='company_merge'),
    path('events/<int:community_id>/', Events.as_view, name='events'),
    path('events/<int:community_id>/add', AddEvent.as_view, name='event_add'),
    path('events/<int:community_id>/tag', tag_event, name='event_tag_form'),
    path('event/<int:event_id>/', EventProfile.as_view, name='event'),
    path('event/<int:event_id>/edit', EditEvent.as_view, name='event_edit'),
    path('event/<int:event_id>/add', AddAttendee.as_view, name='attendee_add'),
]
