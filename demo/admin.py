from django.contrib import admin
from demo.models import Demonstration

# Register your models here.
class DemoAdmin(admin.ModelAdmin):
    list_display = ["community", "status", "created", "expires"]
    list_filter = ["status", "created", "expires"]
    search_fields = ["community__name", "owner__username"]

admin.site.register(Demonstration, DemoAdmin)