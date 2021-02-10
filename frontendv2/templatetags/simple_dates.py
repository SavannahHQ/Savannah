from django import template
import datetime

register = template.Library()

@register.filter(name="dateortime")
def date_or_time(value):
    if value.date() == datetime.datetime.utcnow().date():
        return value.time()
    else:
        return value.date()