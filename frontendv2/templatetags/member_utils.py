from django import template
from django.utils.safestring import mark_safe
from django.templatetags.static import static

from corm.models import *

register = template.Library()

@register.filter
def icon(icon_url, default="img/user-default.png"):
    if icon_url and icon_url[:8] == 'https://':
        html = '<img class="rounded mr-1" src="%s" onerror="this.src=\'%s\';" height="32" width="32" />' % (icon_url, static(default))
    else:
        html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static(default)
    return mark_safe(html)

@register.filter
def avatar_icon(member):
    if member.avatar_url and member.avatar_url.startswith('http'):
        html = '<img class="rounded mr-1" src="%s" onerror="this.src=\'%s\';" height="32" width="32" />' % (member.avatar_url, static('img/user-default.png'))
    else:
        if member.role == Member.STAFF:
            html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static('img/user-staff.png')
        elif member.role == Member.BOT:
            html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static('img/user-bot.png')
        else:
            html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static('img/user-default.png')
    return mark_safe('<span class="avatar-group">' + html +'</span>')

@register.filter
def avatar(member):
    if member.avatar_url and member.avatar_url.startswith('http'):
        html = '<img class="rounded mr-1" src="%s" onerror="this.src=\'%s\';" height="32" width="32" />' % (member.avatar_url, static('img/user-default.png'))
    else:
        if member.role == Member.STAFF:
            html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static('img/user-staff.png')
        elif member.role == Member.BOT:
            html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static('img/user-bot.png')
        else:
            html = '<img class="rounded mr-1" src="%s" height="32" width="32" />' % static('img/user-default.png')
    if member.company and member.company.icon_url:
        html += '<img title="%s" class="icon-badge rounded mr-1 small" src="%s" />' % (member.company.name, member.company.icon_url)
    return mark_safe('<span class="avatar-group">' + html +'</span>')

