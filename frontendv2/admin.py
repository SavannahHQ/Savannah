from django.contrib import admin
from frontendv2.models import EmailRecord, ManagerInvite, PasswordResetRequest

# Register your models here.
class EmailAdmin(admin.ModelAdmin):
    list_display = ["when", "recipient_display", "category", "subject", "sender", "ok"]
    list_filter = ["ok", "when", "category", ("sender", admin.RelatedOnlyFieldListFilter)]
    readonly_fields = ["when", "sender", "member", "email", "subject", "body", "category", "ok"]
    search_fields = ["subject", "body", "to"]

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

class ManagerInviteAdmin(admin.ModelAdmin):
    list_display = ("community", "email", "invited_by", "timestamp", "expires")
    list_filter = ("community", "invited_by", "timestamp", "expires")
admin.site.register(ManagerInvite, ManagerInviteAdmin)

class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ("user", "email",  "timestamp", "expires")
    list_filter = ("timestamp", "expires")
admin.site.register(PasswordResetRequest, PasswordResetAdmin)

