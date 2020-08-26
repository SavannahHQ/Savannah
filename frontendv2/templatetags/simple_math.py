from django import template

register = template.Library()

@register.filter
def add(value, arg):
    return value + arg

@register.filter
def subtract(value, arg):
    return value - arg

@register.filter(name='abs')
def abs_filter(value):
    return abs(value)