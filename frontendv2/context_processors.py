from django.conf import settings

from . import colors as savannah_colors


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
