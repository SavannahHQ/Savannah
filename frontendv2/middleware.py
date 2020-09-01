import json

from django.utils.deprecation import MiddlewareMixin
from django.utils.safestring import SafeData, mark_safe

from notifications.models import Notification

class ReadNotificationMiddleware(MiddlewareMixin):
    """
    Middleware that marks notifications as read when you view the page they link to
    """

    def process_response(self, request, response):
        if request.user.is_authenticated:
            unread = Notification.objects.filter(unread=True, recipient=request.user, data__contains=request.path)
            unread.update(unread=False)
        return response
