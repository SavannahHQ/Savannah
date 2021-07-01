from django import template
from django.utils.safestring import mark_safe

from corm.models import *

register = template.Library()

@register.filter
def icon(icon_url, default="fas fa-user"):
    if icon_url and icon_url[:8] == 'https://':
        html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % icon_url
    else:
       html = '<span class="badge mr-1"><i class="%s avatar-icon text-muted"></i></span>' % default
    return mark_safe(html)

@register.filter
def avatar_icon(avatar_url, default="fas fa-user"):
    if avatar_url and avatar_url[:8] == 'https://':
        html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % avatar_url
    else:
       html = '<span class="badge mr-1"><i class="%s avatar-icon text-muted"></i></span>' % default
    return mark_safe(html)

@register.filter
def avatar(member):
    if member.avatar_url and member.avatar_url.startswith('http'):
        html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % member.avatar_url
    else:
        if member.role == Member.STAFF:
            default = 'fas fa-user-tie'
        elif member.role == Member.BOT:
            default = 'fas fa-bot'
        else:
            default = 'fas fa-user'
        html = '<span class="badge mr-1"><i class="%s avatar-icon text-muted"></i></span>' % default
    if member.company and member.company.icon_url:
        html += '<img title="%s" class="icon-badge rounded mr-1 small" src="%s" />' % (member.company.name, member.company.icon_url)
    return mark_safe('<span class="avatar-group">' + html +'</span>')

