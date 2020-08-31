from django.contrib import admin

from billing.models import Company, Management

# Register your models here.
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'email')
admin.site.register(Company, CompanyAdmin)

class ManagementAdmin(admin.ModelAdmin):
    list_display = ('company', 'community')
admin.site.register(Management, ManagementAdmin)

