import csv
from django.http import HttpResponse
from django.contrib import admin
from django.utils.safestring import mark_safe
from demo.models import Demonstration, DemoLog

# Register your models here.
class DemoAdmin(admin.ModelAdmin):
    list_display = ["community", "link", "status", "created", "expires"]
    list_filter = ["status", "created", "expires"]
    search_fields = ["community__name", "owner__username"]

    def link(self, demo):
        return mark_safe("<a href=\"/dashboard/%s\" target=\"_blank\">View</a>" % demo.community.id)
    link.short_description = "Dashboard"

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()


admin.site.register(Demonstration, DemoAdmin)

class DemoLogAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at", "deleted_at"]
    list_filter = ["created_at", "deleted_at"]
    search_fields = ["name", "created_by__username"]
    actions = ('download_owners',)
    date_hierarchy='created_at'

    def download_owners(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="community_owners.csv"'
        writer = csv.DictWriter(response, fieldnames=['Name', 'Role', 'Email', 'Last Seen', 'Community', 'Community Status'])
        writer.writeheader()
        for log in queryset.all():
            name = log.created_by.username
            email = log.created_by.email
            last_seen = log.created_by.last_login
            community_name = log.name
            writer.writerow({'Name': name, 'Role': 'Owner', 'Email':email, 'Last Seen':last_seen, 'Community':community_name, 'Community Status':'Demonstration'})
        return response
    download_owners.short_description = "Download Owners"

admin.site.register(DemoLog, DemoLogAdmin)