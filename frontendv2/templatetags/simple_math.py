from django import template

register = template.Library()

@register.filter
def add(value, arg):
    return value + arg

@register.filter
def subtract(value, arg):
    return value - arg

@register.filter
def day_duration(value, arg=None):
    count = value
    interval = 'day'
    if value > 366*2 or arg == 'year':
        count = round(value/365.25)
        interval='year'
    elif value > 30.4*3 or arg == 'month':
        count = round(value/30.4)
        interval='month'
    if count != 1:
        interval += "s"
    return "%s %s" % (count, interval)

@register.filter(name='abs')
def abs_filter(value):
    return abs(value)