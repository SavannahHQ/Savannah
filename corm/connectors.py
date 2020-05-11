from django.conf import settings

class ConnectionManager(object):

    CONNECTOR_CHOICES=  [
            ("corm.plugins.null", "Manual Entry"),
            ("corm.plugins.reddit", "Reddit"),
            ("corm.plugins.twitter", "Twitter"),
        ]

    CONNECTOR_PLUGINS = dict()
    CONNECTOR_IMPORTERS = dict()

    @classmethod 
    def add_plugin(cls, namespace, plugin):
        cls.CONNECTOR_PLUGINS[namespace] = plugin
        importer_cmd_name = plugin.get_import_command_name()
        if importer_cmd_name:
            cls.CONNECTOR_IMPORTERS[importer_cmd_name] = plugin
        cls.CONNECTOR_CHOICES.append((namespace, plugin.get_source_type_name()))

    @classmethod
    def get_identity_url(cls, contact):
        connector = contact.source.connector
        if connector in cls.CONNECTOR_PLUGINS:
            plugin  = cls.CONNECTOR_PLUGINS[connector]
            return plugin.get_identity_url(contact)

        if connector == "corm.plugins.github":
            return "https://github.com/%s" % contact.detail
        if connector == "corm.plugins.reddit":
            return "https://reddit.com/u/%s" % contact.detail
        if connector == "corm.plugins.twitter":
            return "https://twitter.com/%s" % contact.detail
        return None