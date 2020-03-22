from django.conf import settings

class ConnectionManager(object):

    CONNECTOR_CHOICES=  [
            ("corm.plugins.null", "Manual Entry"),
            ("corm.plugins.email", "Email"),
            ("corm.plugins.slack", "Slack"),
            ("corm.plugins.discourse", "Discourse"),
            ("corm.plugins.rss", "RSS"),
            ("corm.plugins.reddit", "Reddit"),
            ("corm.plugins.github", "Github"),
        ]