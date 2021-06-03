from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def avatar_icon(avatar_url):
    if avatar_url and avatar_url[:8] == 'https://':
        html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % avatar_url
    else:
       html = '<span class="badge"><i class="fas fa-user avatar-icon text-muted"></i></span>'
    return mark_safe(html)