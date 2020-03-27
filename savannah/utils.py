from corm.models import Source, Community

def add_slack_source(request, api_data):
    access_token = api_data.get("access_token")
    Source.objects.get_or_create(connector="corm.plugins.slack", auth_secret=access_token, defaults={
        "community": Community.objects.get(id=request.session["community"]),
        "name": api_data.get("team_name"),
    })
    return request, api_data