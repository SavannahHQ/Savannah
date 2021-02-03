from django.conf import settings
from collections import OrderedDict

class ConnectionManager(object):

    CONNECTOR_CHOICES=  [
            ("corm.plugins.null", "Manual Entry"),
            ("corm.plugins.api", "API"),
        ]

    CONNECTOR_PLUGINS = OrderedDict()
    CONNECTOR_IMPORTERS = OrderedDict()
    CONNECTOR_MAP_CACHE = None

    @classmethod
    def display_name(cls, connector_name):
        if cls.CONNECTOR_MAP_CACHE is None:
            cls.CONNECTOR_MAP_CACHE = dict()
            for key, value in cls.CONNECTOR_CHOICES:
                cls.CONNECTOR_MAP_CACHE[key] = value
        return cls.CONNECTOR_MAP_CACHE[connector_name]

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