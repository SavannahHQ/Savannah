from django.conf import settings
from . import colors as savannah_colors

def fonts(request):
    """
    Return a lazy 'messages' context variable as well as
    'DEFAULT_MESSAGE_LEVELS'.
    """
    return {
        "FONTAWESOME_KIT_URL": getattr(settings, 'FONTAWESOME_KIT_URL', 'https://kit.fontawesome.com/a160749d77.js'),

    }

def colors(request):
    """
    Adds Savannah color classes
    """

    return {'colors': savannah_colors}
