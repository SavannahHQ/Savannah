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


def company_logos(request):
    """
    Adds attribution for the company logo provider, see COMPANY_LOGO_URL
    """
    if not getattr(settings, 'COMPANY_LOGO_URL', ''):
        return {}
    return {
        'company_logo_attribution': getattr(settings, 'COMPANY_LOGO_ATTRIBUTION', ''),
        'company_logo_attribution_url': getattr(settings, 'COMPANY_LOGO_ATTRIBUTION_URL', ''),
    }
