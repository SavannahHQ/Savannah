from django.contrib import admin
from django.utils import timezone
from django.utils.safestring import mark_safe

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
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "member_count", "managers", "owner")
    list_filter = ("owner",)
    search_fields = ("name", "owner")
    def member_count(self, community):
        return community.member_set.all().count()
    member_count.short_description = "Members"

admin.site.register(Community, CommunityAdmin)

class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "color_display", "community", "icon")
    list_filter = ("community",)
    def color_display(self, tag):
        return mark_safe("<span style=\"padding: 3px; background-color: #%s\">%s</span>" % (tag.color, tag.color))
admin.site.register(Tag, TagAdmin)

class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "server", "connector", "community", "contact_count", "activity_count", "conversation_count", "last_import")
    list_filter = ("connector", "community",)

    def contact_count(self, source):
        return source.contact_set.all().count()
    contact_count.short_description = "Contacts"

    def activity_count(self, source):
        return Activity.objects.filter(activity_type__source=source).count()
    activity_count.short_description = "Activity"

    def conversation_count(self, source):
        return Conversation.objects.filter(channel__source=source).count()
    conversation_count.short_description = "Conversations"

admin.site.register(Source, SourceAdmin)

class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "conversation_count")
    list_filter = ("source__community", "source",)
    search_fields = ("name",)

    def conversation_count(self, channel):
        return channel.conversation_set.all().count()
    conversation_count.short_description = "Conversations"

admin.site.register(Channel, ChannelAdmin)

class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "member_count", "task_count")
    list_filter = ("community",)
    search_fields = ("name",)
    def task_count(self, project):
        count = project.task_set.filter(done__isnull=True).count()
        if count > 0:
            count = mark_safe("<a href=\"/admin/corm/task/?project__id__exact=%s\">%s</a>" % (project.id, count))
        return count
    task_count.short_description = "Open Tasks"

    def member_count(self, project):
        return project.collaborators.all().count()
    member_count.short_description = "Collaborators"
admin.site.register(Project, ProjectAdmin)

class MemberConnectionAdmin(admin.ModelAdmin):
    list_display = ("from_member", "to_member", "via", "first_connected", "last_connected")
    list_filter = ("via__community", "via")
admin.site.register(MemberConnection, MemberConnectionAdmin)

class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "user_email", "community", "date_added", "task_count", "conversation_count", "connection_count")
    list_filter = ("community", "tags")
    search_fields = ("name",)
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
    list_display = ("detail", "source", "member")
    list_filter = ("source__connector", "member__community", "source")
    search_fields = ("name",)

admin.site.register(Contact, ContactAdmin)

class ConversationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "channel", "timestamp", "link", "participant_list", "tag_list")
    list_filter = ("channel__source__community", "channel__source__connector", "timestamp", "channel", "tags")
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

class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "source", "feed")
    list_filter = ("source__connector", "community", "source")
admin.site.register(ActivityType, ActivityTypeAdmin)

class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "activity_type", "timestamp")
    list_filter = ("activity_type__source__connector", "activity_type", "tags", "timestamp")
admin.site.register(Activity, ActivityAdmin)

class NoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "member", "author", "timestamp")
    list_filter = ("author", "tags", "member")
admin.site.register(Note, NoteAdmin)