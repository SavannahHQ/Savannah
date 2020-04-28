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
            ("corm.plugins.twitter", "Twitter"),
        ]

    def get_identity_url(contact):
        connector = contact.source.connector
        if connector == "corm.plugins.github":
            return "https://github.com/%s" % contact.detail
        if connector == "corm.plugins.reddit":
            return "https://reddit.com/u/%s" % contact.detail
        if connector == "corm.plugins.twitter":
            return "https://twitter.com/%s" % contact.detail
        if connector == "corm.plugins.discourse":
            return "%s/u/%s" % (contact.source.server, contact.detail)
        return None