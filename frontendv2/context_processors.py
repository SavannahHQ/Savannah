from . import colors as savannah_colors


def colors(request):
    """
    Adds Savannah color classes
    """

    return {'colors': savannah_colors}
