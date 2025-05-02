from django.dispatch import Signal

hook_event = Signal(providing_args=['community', 'event', 'payload'])

