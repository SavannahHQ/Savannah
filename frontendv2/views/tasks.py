import datetime
from icalendar import Calendar, Event, Todo
from django_ical.views import ICalFeed

from django.utils.feedgenerator import SyndicationFeed
from django.shortcuts import reverse
from django.conf import settings

FEED_FIELD_MAP = (
    ("product_id", "prodid"),
    ("method", "method"),
    ("title", "x-wr-calname"),
    ("description", "x-wr-caldesc"),
    ("timezone", "x-wr-timezone"),
    (
        "ttl",
        "x-published-ttl",
    ),  # See format here: http://www.rfc-editor.org/rfc/rfc2445.txt (sec 4.3.6)
)

ITEM_TODO_FIELD_MAP = (
    # 'item_guid' becomes 'unique_id' when passed to the SyndicationFeed
    ("unique_id", "uid"),
    ("title", "summary"),
    ("description", "description"),
    ("start_datetime", "dtstart"),
    ("due_datetime", "due"),
    ("updateddate", "last-modified"),
    ("created", "created"),
    ("timestamp", "dtstamp"),
    ("location", "location"),
    ("geolocation", "geo"),
    ("link", "url"),
    ("organizer", "organizer"),
    ("categories", "categories"),
    ("rrule", "rrule"),
    ("exrule", "exrule"),
    ("rdate", "rdate"),
    ("exdate", "exdate"),
    ("status", "status"),
    ("attendee", "attendee"),
)
class TodoFeed(SyndicationFeed):
    """
    iCalendar 2.0 Feed implementation.
    """

    mime_type = "text/calendar; charset=utf8"

    def write(self, outfile, encoding):  # pylint: disable=unused-argument
        """
        Writes the feed to the specified file in the
        specified encoding.
        """
        cal = Calendar()
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")

        for ifield, efield in FEED_FIELD_MAP:
            val = self.feed.get(ifield)
            if val is not None:
                cal.add(efield, val)

        self.write_items(cal)

        to_ical = getattr(cal, "as_string", None)
        if not to_ical:
            to_ical = cal.to_ical
        outfile.write(to_ical())

    def write_items(self, calendar):
        """
        Write all todos to the calendar
        """
        for item in self.items:
            todo = Todo()
            for ifield, efield in ITEM_TODO_FIELD_MAP:
                val = item.get(ifield)
                if val is not None:
                    if ifield == "attendee":
                        for list_item in val:
                            todo.add(efield, list_item)
                    else:
                        todo.add(efield, val)
            calendar.add_component(todo)

class AbstractTaskCalendarFeed(ICalFeed):
        
    def item_guid(self, task):
        return "task-%s@%s" % (task.id, settings.SITE_DOMAIN)

    def item_link(self, task):
        return reverse('manager_task_edit', kwargs={'community_id':task.community.id, 'task_id':task.id})

    def item_title(self, task):
        return task.name

    def item_description(self, task):
        return task.detail

    def item_start_datetime(self, task):
        return task.due

    def item_end_datetime(self, task):
        return task.due + datetime.timedelta(minutes=15)

    def __call__(self, request, *args, **kwargs):
        response = ICalFeed.__call__(self, request, *args, **kwargs)
        response["Access-Control-Allow-Origin"] = "*"
        return response
