import csv
from django.http import HttpResponse
    
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

def isNotZero(parameter_name, title=None):
    if title is None:
        title = "has %s" % parameter_name

    class NotZeroFilter(admin.SimpleListFilter):

        def lookups(self, request, model_admin):
            return (
                ('1', 'True'),
                ('0', 'False'),
            )

        def queryset(self, request, queryset):
            if self.value() == '1':
                filter_string = self.parameter_name + '__gte'
                has_positive_value = {
                    filter_string: 1
                }
                return queryset.filter(**has_positive_value)
            if self.value() == '0':
                filter_string = self.parameter_name
                has_zero_value = {
                    filter_string: 0
                }
                return queryset.filter(**has_zero_value)

    NotZeroFilter.title = title
    NotZeroFilter.parameter_name = parameter_name
    return NotZeroFilter

# Register your models here.

class UserAuthAdmin(admin.ModelAdmin):
    list_display = ("user", "connector", "server", "auth_id")
    list_filter = ("user", "connector")
admin.site.register(UserAuthCredentials, UserAuthAdmin)

class CommunityAdmin(admin.ModelAdmin):
    list_display = ("logo_icon", "name", "link", "member_count", "source_count", "channel_count", "owner", "created", "status")
    list_display_links = ("name",)
    list_filter = ("status", "created")
    search_fields = ("name", "owner__username", "owner__email")
    actions = ('download_owners',)
    date_hierarchy='created'
    ordering = ('-created',)

    def get_queryset(self, request):
        qs = super(CommunityAdmin, self).get_queryset(request)
        qs = qs.annotate(member_count=Count('member', distinct=True))
        qs = qs.annotate(source_count=Count('source', distinct=True))
        return qs

    def download_owners(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="community_owners.csv"'
        writer = csv.DictWriter(response, fieldnames=['Name', 'Role', 'Email', 'Last Seen', 'Community', 'Community Status'])
        writer.writeheader()
        for community in queryset.all():
            name = community.owner.username
            email = community.owner.email
            last_seen = community.owner.last_login
            try:
                manager_profile = ManagerProfile.objects.get(community=community, user=community.owner)
                name = str(manager_profile)
                email = manager_profile.email
                last_seen = manager_profile.last_seen or last_seen
            except:
                pass
            writer.writerow({'Name': name, 'Role': 'Owner', 'Email':email, 'Last Seen':last_seen, 'Community':community.name, 'Community Status':Community.STATUS_NAMES[community.status]})
        return response
    download_owners.short_description = "Download Owners"

    def logo_icon(self, community):
        return mark_safe("<img src=\"%s\" />" % community.icon_path)
    logo_icon.short_description = "Icon"

    def member_count(self, community):
        return community.member_count
    member_count.short_description = "Members"
    member_count.admin_order_field = 'member_count'

    def source_count(self, community):
        return community.source_count
    source_count.short_description = "Sources"
    source_count.admin_order_field = 'source_count'

    def channel_count(self, community):
        return Channel.objects.filter(source__community=community).count()
    channel_count.short_description = "Channels"

    def link(self, community):
        return mark_safe("<a href=\"/dashboard/%s\" target=\"_blank\">View</a>" % community.id)
    link.short_description = "Dashboard"

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
    list_display = ("name", "color_display", "community", "keywords", "last_changed", "connector_name", "editable")
    list_filter = ("editable", "connector", "community", "last_changed")
    form = TagAdminForm
    def color_display(self, tag):
        return mark_safe("<span style=\"padding: 3px; background-color: #%s\">%s</span>" % (tag.color, tag.color))
admin.site.register(Tag, TagAdmin)

class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled", "status", "icon_name", "connector", "community", "contact_count", "contribution_count", "conversation_count", "first_import", "last_import")
    list_filter = (isNotZero("import_failed_attempts", "import failures"), "connector", "community", "enabled", "first_import", "last_import")
    date_hierarchy='first_import'

    def status(self, source):
        if source.import_failed_attempts > 0:
            return mark_safe('<img src="%sadmin/img/icon-no.svg" title="%s">' % (settings.STATIC_URL, source.import_failed_message))
        else:
            return mark_safe('<img src="%sadmin/img/icon-yes.svg" title="ok">' % settings.STATIC_URL)
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
    list_display = ("name", "enabled", "status", "source", "conversation_count", "first_import", "last_import", "oldest_import")
    list_filter = (isNotZero("import_failed_attempts", "import failures"), "source__community", "source__connector", "enabled", "first_import", "last_import")
    search_fields = ("name",)
    date_hierarchy='first_import'

    def status(self, channel):
        if channel.import_failed_attempts > 0:
            return mark_safe('<img src="%sadmin/img/icon-no.svg" title="%s">' % (settings.STATIC_URL, channel.import_failed_message))
        else:
            return mark_safe('<img src="%sadmin/img/icon-yes.svg" title="ok">' % settings.STATIC_URL)

    def conversation_count(self, channel):
        return channel.conversation_set.all().count()
    conversation_count.short_description = "Conversations"

admin.site.register(Channel, ChannelAdmin)

class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "default_project", "owner", "member_count", "task_count")
    list_filter = ("community","default_project")
    search_fields = ("name",)
    raw_id_fields = ('owner',)
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
    list_display = ("member", "community", "project", "level", "conversation_count", "contribution_count", "timestamp")
    list_filter = ("community", "level", "member__role", "project", "timestamp")
    raw_id_fields = ('member',)
admin.site.register(MemberLevel, LevelAdmin)

class MemberConnectionAdmin(admin.ModelAdmin):
    list_display = ("from_member", "to_member", "connection_count", "community", "first_connected", "last_connected")
    list_filter = ("community", "last_connected")
    raw_id_fields = ("from_member", "to_member")
admin.site.register(MemberConnection, MemberConnectionAdmin)

class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "role", "first_seen", "last_seen")
    list_filter = ("community", "role", "first_seen", "last_seen")
    search_fields = ("name", "email_address", "contact__detail")

    def user_email(self, member):
        if member.user is not None:
            return member.user.email
        return ""
    user_email.short_description = "Email"

admin.site.register(Member, MemberAdmin)

class MergedMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'community', 'merged_with', 'merged_date')
    list_filter = ('community', 'merged_date')
    raw_id_fields = ('merged_with',)
    actions = ('restore',)
    def restore(self, request, queryset):
        for merge in queryset:
            merge.restore()
    restore.short_description = "Restore to Member"

admin.site.register(MemberMergeRecord, MergedMemberAdmin)

class MemberWatchAdmin(admin.ModelAdmin):
    list_display = ('manager', 'member', 'start', 'end', 'level')
    list_filter = ('manager', 'member__community', 'level', 'start', 'end')
admin.site.register(MemberWatch, MemberWatchAdmin)

class ContactAdmin(admin.ModelAdmin):
    list_display = ("detail", "source", "member", "name", "email_address")
    list_filter = ("source__connector", "member__community", "source")
    search_fields = ("detail","email_address")
    raw_id_fields = ("member",)

admin.site.register(Contact, ContactAdmin)

class ActivityAdmin(admin.ModelAdmin):
    list_display = ("short_description", "member", "channel", "timestamp", "link")
    list_filter = ("short_description", "channel__source__community", "channel__source__connector", "timestamp")
    search_fields = ("short_description","long_description", "member__name")
    raw_id_fields = ('member', 'conversation', 'contribution', 'event_attendance')
    def link(self, conversation):
        if conversation.location is not None:
            return mark_safe("<a href=\"%s\">Open</a>" % conversation.location)
        else:
            return ""
    link.short_description = "Location"
admin.site.register(Activity, ActivityAdmin)

class ConversationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "channel", "timestamp", "link", "participant_list", "tag_list")
    list_filter = ("channel__source__community", "channel__source__connector", "timestamp")
    search_fields = ("content",)
    raw_id_fields = ('channel', 'source', 'speaker', 'thread_start', 'contribution', 'links')
    date_hierarchy='timestamp'

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

class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'community', 'conversation', 'member', 'initiator')
    list_filter = ('community',)
    raw_id_fields = ('conversation', 'member', 'initiator')
    search_fields = ('conversation__content', 'member__name', 'initiator__name')
admin.site.register(Participant, ParticipantAdmin)

class TaskAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "due", "community", "project", "stakeholder_list", "is_done")
    list_filter = (isNotNull("done"), "community", "owner", "project", "tags", "stakeholders")
    raw_id_fields = ('stakeholders', 'conversation')
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
    list_filter = ("contribution_type__source__connector", "community", "contribution_type__name", "timestamp")
    raw_id_fields = ('author',)
    date_hierarchy='timestamp'

    def tag_list(self, contribution):
        return ", ".join([tag.name for tag in contribution.tags.all()[:10]])
    tag_list.short_description = "Tags"
admin.site.register(Contribution, ContributionAdmin)

class PromotionAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "timestamp", "tag_list")
    list_filter = ("channel__source__connector", "community", "timestamp")
    raw_id_fields = ('promoters','conversation')
    def tag_list(self, promotion):
        return ", ".join([tag.name for tag in promotion.tags.all()[:10]])
    tag_list.short_description = "Tags"
admin.site.register(Promotion, PromotionAdmin)

class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "attendee_count", "community", "source", "channel", "start_timestamp", "end_timestamp", "tag")
    list_filter = ("source__connector", "community", "start_timestamp")
    raw_id_fields = ("source", "channel")
    date_hierarchy='start_timestamp'

    def attendee_count(self, event):
        return event.rsvp.count()
    attendee_count.short_description = "Attendees"

admin.site.register(Event, EventAdmin)

class EventAttendeeAdmin(admin.ModelAdmin):
    list_display = ("member", "role", "event", "community", "timestamp")
    list_filter = ("role", "event__source__connector", "community", "timestamp")
    raw_id_fields = ("member",)
    date_hierarchy='timestamp'

admin.site.register(EventAttendee, EventAttendeeAdmin)

class NoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "member", "author", "timestamp")
    list_filter = ("author", "timestamp")
    search_fields = ("content", "member__name")
    raw_id_fields = ('member','author', 'tags')
    date_hierarchy='timestamp'
admin.site.register(Note, NoteAdmin)

class GiftTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "impact", "discontinued")
    list_filter = ("community", "discontinued")
admin.site.register(GiftType, GiftTypeAdmin)

class GiftAdmin(admin.ModelAdmin):
    list_display = ("gift_type", "member", "impact", "community", "sent_date")
    list_filter = ("community", "gift_type", "sent_date")
    date_hierarchy='sent_date'

admin.site.register(Gift, GiftAdmin)

class SuggestTagAdmin(admin.ModelAdmin):
    list_display = ("keyword", "score", "community", "reason", "created_at", "actioned_at", "status")
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

admin.site.register(SuggestTag, SuggestTagAdmin)

class SuggestTaskAdmin(admin.ModelAdmin):
    list_display = ("stakeholder", "due_in_days", "project", "community", "reason", "created_at", "actioned_at", "status")
    list_filter = ("community", "status", "actioned_at", "created_at")
    actions = ("accept", "ignore", "reject")
    raw_id_fields = ('stakeholder','project')
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

admin.site.register(SuggestTask, SuggestTaskAdmin)

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
class SuggestContributionAdmin(admin.ModelAdmin):
    list_display = ("reason", "contribution_type", "community", "timestamp", "actioned_at", "status")
    list_filter = ("community", "source", "status", "actioned_at", "created_at")
    raw_id_fields = ("conversation","activity")
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

    def timestamp(self, suggestion):
        return suggestion.conversation.timestamp
    timestamp.short_description = "Convo Timestamp"

admin.site.register(SuggestConversationAsContribution, SuggestContributionAdmin)

class SuggestCompanyAdmin(admin.ModelAdmin):
    list_display = ("domain", "community", "reason", "created_at", "actioned_at", "status")
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

admin.site.register(SuggestCompanyCreation, SuggestCompanyAdmin)


class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "report_type", "community", "generated")
    list_filter = ("community", "report_type", "generated")
    date_hierarchy='generated'

admin.site.register(Report, ReportAdmin)

class ManagersAdmin(admin.ModelAdmin):
    list_display = ('user', 'community', 'link', 'last_seen', 'send_notifications', 'member', 'realname', 'contact_email')
    list_filter = ('last_seen', 'community__status', 'community', 'send_notifications')
    raw_id_fields = ('member',)
    actions = ('download_managers',)
    date_hierarchy='last_seen'
    def download_managers(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="community_managers.csv"'
        writer = csv.DictWriter(response, fieldnames=['Name', 'Role', 'Email', 'Last Seen', 'Community', 'Community Status'])
        writer.writeheader()
        for manager_profile in queryset.all():
            name = str(manager_profile)
            email = manager_profile.email
            last_seen = manager_profile.last_seen or manager_profile.user.last_login
            role = 'Manager'
            if manager_profile.user == manager_profile.community.owner:
                role = 'Owner'
            writer.writerow({'Name': name, 'Role':role, 'Email':email, 'Last Seen':last_seen, 'Community':manager_profile.community.name, 'Community Status':Community.STATUS_NAMES[manager_profile.community.status]})
        return response
    download_managers.short_description = "Download Managers"

    def link(self, profile):
        return mark_safe("<a href=\"/dashboard/%s\" target=\"_blank\">View</a>" % profile.community.id)
    link.short_description = "Dashboard"

admin.site.register(ManagerProfile, ManagersAdmin)

class CompanyDomainAdmin(admin.ModelAdmin):
#     list_display = ("domain", "company", "community")
#     list_filter = ("community",)
    pass
admin.site.register(CompanyDomains, CompanyDomainAdmin)

class SourceGroupAdmin(admin.ModelAdmin):
#     list_display = ("name", "community", "source")
#     list_filter = ("source__connector", "community")
    pass
admin.site.register(SourceGroup, SourceGroupAdmin)

class CompanyDomainInline(admin.TabularInline):
    model = CompanyDomains
    fk_name = "company"

class SourceGroupsInline(admin.TabularInline):
    model = SourceGroup
    fk_name = "company"

class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "community", "tag", "members", "is_staff")
    list_filter = ("community", "is_staff")
    inlines = [
        CompanyDomainInline,
        SourceGroupsInline,
    ]

    def members(self, company):
        return Member.objects.filter(company=company).count()

admin.site.register(Company, CompanyAdmin)

class EmailAdmin(admin.ModelAdmin):
    list_display = ["when", "recipient_display", "category", "subject", "sender", "ok"]
    list_filter = ["ok", "when", "category", ("sender", admin.RelatedOnlyFieldListFilter)]
    readonly_fields = ["when", "sender", "member", "email", "subject", "body", "category", "ok"]
    search_fields = ["subject", "body", "member__name"]
    date_hierarchy='when'

    def recipient_display(self, record):
        if record.member is not None:
            return "%s <%s>" % (record.member.name, record.email)
        else:
            return record.email

    recipient_display.short_description = "To"

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False


admin.site.register(EmailRecord, EmailAdmin)

class HyperlinkAdmin(admin.ModelAdmin):
    list_display = ["url", "ignored", "host", "content_type"]
    list_filter = ["ignored", "community", "content_type", "host"]
    search_fields = ["url"]
admin.site.register(Hyperlink, HyperlinkAdmin)

class InsightAdmin(admin.ModelAdmin):
    list_display = ("uid", "level", "community", "recipient", "unread", "timestamp")
    list_filter = ("unread", "community", "level", "timestamp")
    search_fields = ["uid"]
admin.site.register(Insight, InsightAdmin)

class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "uploaded_by", "uploaded_at")
    list_filter = ("status", "community", "uploaded_by", "uploaded_at")
    raw_id_fields = ("event", )
    search_fields = ["uploaded_to"]
admin.site.register(UploadedFile, UploadedFileAdmin)

class OpportunityHistoryInline(admin.TabularInline):
    model = OpportunityHistory
    fk_name = "opportunity"
    extra=0

class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "contribution_type", "community", "created_by", "created_at")
    list_filter = ("status", "community", "created_at", "closed_at")
    search_fields = ("name", )
    raw_id_fields = ('member', 'source', 'contribution_type', 'activities')
    inlines = [
        OpportunityHistoryInline,
    ]
admin.site.register(Opportunity, OpportunityAdmin)

from django.forms import BaseInlineFormSet
class LimitModelFormset(BaseInlineFormSet):
    """ Base Inline formset to limit inline Model query results. """
    def __init__(self, *args, **kwargs):
        super(LimitModelFormset, self).__init__(*args, **kwargs)
        _kwargs = {self.fk.name: kwargs['instance']}
        self.queryset = kwargs['queryset'].filter(**_kwargs).order_by(*self.model._meta.ordering)[:20]

class WebhookEventInline(admin.TabularInline):
    model=WebHookEvent
    fields = ('created', 'event', 'payload', 'success')
    readonly_fields = ('created', 'event', 'payload', 'success')
    show_change_link = True
    formset = LimitModelFormset

    def has_change_permission(self, request, obj=None):
        return False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WebHook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ('event', 'community', 'user', 'target')
    list_filter = ('community',)
    readonly_fields = ('secret',)
    inlines = [WebhookEventInline]

class WebhookEventLogInline(admin.TabularInline):
    model=WebHookEventLog
    fields = ('timestamp', 'status', 'response')
    readonly_fields = ('timestamp', 'status', 'response')
    show_change_link = True
    formset = LimitModelFormset
    def has_change_permission(self, request, obj=None):
        return False
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WebHookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('created', 'hook', 'event', 'success')
    list_filter = ('event', 'hook__community')
    inlines = [WebhookEventLogInline]

@admin.register(WebHookEventLog)
class WebookEventLog(admin.ModelAdmin):
    list_display = ('timestamp', 'event', 'status')
    list_filter = ('event__event', 'event__hook__community')
