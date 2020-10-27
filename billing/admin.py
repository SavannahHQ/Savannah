from django.contrib import admin

from billing.models import Organization, Management

# Register your models here.
class OrgAdmin(admin.ModelAdmin):
    list_display = ('name', 'email')
admin.site.register(Organization, OrgAdmin)

class ManagementAdmin(admin.ModelAdmin):
    list_display = ('org', 'community')
admin.site.register(Management, ManagementAdmin)

