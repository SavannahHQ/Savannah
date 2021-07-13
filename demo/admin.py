from django.contrib import admin
from django.utils.safestring import mark_safe
from demo.models import Demonstration

# Register your models here.
class DemoAdmin(admin.ModelAdmin):
    list_display = ["community", "link", "status", "created", "expires"]
    list_filter = ["status", "created", "expires"]
    search_fields = ["community__name", "owner__username"]

    def link(self, demo):
        return mark_safe("<a href=\"/dashboard/%s\" target=\"_blank\">View</a>" % demo.community.id)
    link.short_description = "Dashboard"
admin.site.register(Demonstration, DemoAdmin)