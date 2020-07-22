from django.contrib import admin
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.forms import ModelForm
from django.forms.widgets import TextInput

from .models import *

def isNotNull(parameter_name, title=None):
    if title is None:
        title = parameter_name

    class NotNullFilter(admin.SimpleListFilter):

        def lookups(self, request, model_admin):
            return (
                ('not_null', 'True'),
                ('null', 'False'),
            )

        def queryset(self, request, queryset):
            filter_string = self.parameter_name + '__isnull'
            if self.value() == 'not_null':
                is_null_false = {
                    filter_string: False
                }
                return queryset.filter(**is_null_false)

            if self.value() == 'null':
                is_null_true = {
                    filter_string: True
                }
                return queryset.filter(**is_null_true)

    NotNullFilter.title = title
    NotNullFilter.parameter_name = parameter_name
    return NotNullFilter

# Register your models here.

class UserAuthAdmin(admin.ModelAdmin):
    list_display = ("user", "connector", "server", "auth_id")
    list_filter = ("user", "connector")
admin.site.register(UserAuthCredentials, UserAuthAdmin)

class CommunityAdmin(admin.ModelAdmin):
    list_display = ("logo_icon", "name", "member_count", "source_count", "channel_count", "managers", "owner")
    list_display_links = ("name",)
    list_filter = ("owner",)
    search_fields = ("name", "owner")
    def logo_icon(self, community):
        return mark_safe("<img src=\"%s\" />" % community.icon_path)
    logo_icon.short_description = "Icon"

    def member_count(self, community):
        return community.member_set.all().count()
    member_count.short_description = "Members"

    def source_count(self, community):
        return community.source_set.all().count()
    source_count.short_description = "Sources"

    def channel_count(self, community):
        return Channel.objects.filter(source__community=community).count()
    channel_count.short_description = "Channels"

admin.site.register(Community, CommunityAdmin)

class TagAdminForm(ModelForm):
    class Meta:
        model = Tag
        fields = '__all__'
        widgets = {
            'color': TextInput(attrs={'type': 'color'}),
        }
    def __init__(self, *args, **kwargs):
        super(TagAdminForm, self).__init__(*args, **kwargs)
        if 'color' in self.initial:
            self.initial['color'] = '#%s'%self.initial['color']

    def clean_color(self):
        data = self.cleaned_data['color']
        return data.replace('#', '')

class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "color_display", "community", "keywords")
    list_filter = ("community",)
    form = TagAdminForm
    def color_display(self, tag):
        return mark_safe("<span style=\"padding: 3px; background-color: #%s\">%s</span>" % (tag.color, tag.color))
admin.site.register(Tag, TagAdmin)

class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "icon_name", "server", "connector", "community", "contact_count", "contribution_count", "conversation_count", "last_import")
    list_filter = ("connector", "community", "last_import")

    def contact_count(self, source):
        return source.contact_set.all().count()
    contact_count.short_description = "Contacts"

    def contribution_count(self, source):
        return Contribution.objects.filter(contribution_type__source=source).count()
    contribution_count.short_description = "Contributions"

    def conversation_count(self, source):
        return Conversation.objects.filter(channel__source=source).count()
    conversation_count.short_description = "Conversations"

admin.site.register(Source, SourceAdmin)

class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "conversation_count", "last_import")
    list_filter = ("source__community", "source__connector", "last_import")
    search_fields = ("name",)

    def conversation_count(self, channel):
        return channel.conversation_set.all().count()
    conversation_count.short_description = "Conversations"

admin.site.register(Channel, ChannelAdmin)

class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "default_project", "owner", "member_count", "task_count")
    list_filter = ("community","default_project")
    search_fields = ("name",)
    def task_count(self, project):
        count = project.task_set.filter(done__isnull=True).count()
        if count > 0:
            count = mark_safe("<a href=\"/admin/corm/task/?project__id__exact=%s\">%s</a>" % (project.id, count))
        return count
    task_count.short_description = "Open Tasks"

    def member_count(self, project):
        count = project.collaborators.all().count()
        if count > 0:
            count = mark_safe("<a href=\"/admin/corm/memberlevel/?project__id__exact=%s\">%s</a>" % (project.id, count))
        return count
    member_count.short_description = "Collaborators"
admin.site.register(Project, ProjectAdmin)

class LevelAdmin(admin.ModelAdmin):
    list_display = ("member", "community", "project", "level", "timestamp")
    list_filter = ("community", "level", "member__role", "project", "timestamp")
admin.site.register(MemberLevel, LevelAdmin)

class MemberConnectionAdmin(admin.ModelAdmin):
    list_display = ("from_member", "to_member", "via", "first_connected", "last_connected")
    list_filter = ("via__community", "via")
admin.site.register(MemberConnection, MemberConnectionAdmin)

class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "community", "first_seen", "last_seen", "task_count", "conversation_count", "connection_count")
    list_filter = ("community", "role", "first_seen", "last_seen", "tags")
    search_fields = ("name", "email_address", "contact__detail")
    def task_count(self, member):
        count = member.task_set.filter(done__isnull=True).count()
        if count > 0:
            count = mark_safe("<a href=\"/admin/corm/task/?stakeholders__id__exact=%s\">%s</a>" % (member.id, count))
        return count
    task_count.short_description = "Open Tasks"

    def user_email(self, member):
        if member.user is not None:
            return member.user.email
        return ""
    user_email.short_description = "Email"

    def conversation_count(self, member):
        return Conversation.objects.filter(participants=member).count()
    conversation_count.short_description = "Conversations"

    def connection_count(self, member):
        return member.connections.count()
    connection_count.short_description = "Connections"

admin.site.register(Member, MemberAdmin)

class ContactAdmin(admin.ModelAdmin):
    list_display = ("detail", "source", "member", "name", "email_address")
    list_filter = ("source__connector", "member__community", "source")
    search_fields = ("detail",)

admin.site.register(Contact, ContactAdmin)

class ConversationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "channel", "timestamp", "link", "participant_list", "tag_list")
    list_filter = ("channel__source__community", "channel__source__connector", "timestamp", "tags")
    search_fields = ("content",)
    def link(self, conversation):
        if conversation.location is not None:
            return mark_safe("<a href=\"%s\">Open</a>" % conversation.location)
        else:
            return ""
    link.short_description = "Location"
    def participant_list(self, conversation):
        return ", ".join([participant.name for participant in conversation.participants.all()[:10]])
    participant_list.short_description = "Participants"
    def tag_list(self, conversation):
        return ", ".join([tag.name for tag in conversation.tags.all()[:10]])
    tag_list.short_description = "Tags"
admin.site.register(Conversation, ConversationAdmin)

class TaskAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "due", "community", "project", "stakeholder_list", "is_done")
    list_filter = (isNotNull("done"), "community", "owner", "project__community", "project", "tags", "stakeholders")
    actions = ('mark_done',"mark_notdone")
    def stakeholder_list(self, task):
        return ", ".join([member.name for member in task.stakeholders.all()[:10]])
    stakeholder_list.short_description = "Stakeholders"

    def is_done(self, task):
        return task.is_done
    is_done.short_description = "Done"
    def mark_done(self, request, queryset):
        queryset.update(done=timezone.now())
    mark_done.short_description = "Mark as done"

    def mark_notdone(self, request, queryset):
        queryset.update(done=None)
    mark_notdone.short_description = "Mark as not done"
admin.site.register(Task, TaskAdmin)

class ContributionTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "source", "feed")
    list_filter = ("source__connector", "community", "source")
admin.site.register(ContributionType, ContributionTypeAdmin)

class ContributionAdmin(admin.ModelAdmin):
    list_display = ("title", "contribution_type", "channel", "timestamp", "author", "tag_list")
    list_filter = ("contribution_type__source__connector", "community", "contribution_type", "timestamp", "tags")
    raw_id_fields = ('conversation',)
    def tag_list(self, contribution):
        return ", ".join([tag.name for tag in contribution.tags.all()[:10]])
    tag_list.short_description = "Tags"
admin.site.register(Contribution, ContributionAdmin)

class PromotionAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "timestamp", "tag_list")
    list_filter = ("channel__source__connector", "community", "timestamp")
    raw_id_fields = ('promoters',)
    def tag_list(self, promotion):
        return ", ".join([tag.name for tag in promotion.tags.all()[:10]])
    tag_list.short_description = "Tags"
admin.site.register(Promotion, PromotionAdmin)

class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "start_timestamp", "end_timestamp", "tag")
    list_filter = ("source__connector", "community", "start_timestamp")
admin.site.register(Event, EventAdmin)

class NoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "member", "author", "timestamp")
    list_filter = ("author", "tags", "member")
admin.site.register(Note, NoteAdmin)

class SuggestMemberMergeAdmin(admin.ModelAdmin):
    list_display = ("destination_member", "source_member", "community", "reason", "created_at", "actioned_at", "status")
    list_filter = ("community", "status", "actioned_at", "created_at")
    actions = ("accept", "ignore", "reject")
    def accept(self, request, queryset):
        for suggestion in queryset.all():
            suggestion.accept(request.user)
    accept.short_description = "Accept Suggestions"

    def reject(self, request, queryset):
        for suggestion in queryset.all():
            suggestion.reject(request.user)
    reject.short_description = "Reject Suggestions"

    def ignore(self, request, queryset):
        for suggestion in queryset.all():
            suggestion.ignore(request.user)
    ignore.short_description = "Ignore Suggestions"

admin.site.register(SuggestMemberMerge, SuggestMemberMergeAdmin)