from django import template
import datetime

register = template.Library()

@register.filter(name="dateortime")
def date_or_time(value):
    if value is None:
        return ''
    if value.date() == datetime.datetime.utcnow().date():
        return value.time()
    else:
        return value.date()

@register.filter(name="duration")
def duration_as_text(timedeltaobj):
    """Convert a datetime.timedelta object into Days, Hours, Minutes, Seconds."""
    if timedeltaobj is None:
        return None
    secs = timedeltaobj.total_seconds()
    timetot = ""
    if secs > 86400: # 60sec * 60min * 24hrs
        days = secs // 86400
        timetot += "{} days ".format(int(days))
        secs = secs - days*86400

    if secs > 3600:
        hrs = secs // 3600
        timetot += " {} hrs".format(int(hrs))
        secs = secs - hrs*3600

    if secs > 60:
        mins = secs // 60
        timetot += " {} mins".format(int(mins))
        secs = secs - mins*60

    return timetot