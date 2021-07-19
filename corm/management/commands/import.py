from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import subprocess
import requests
from time import sleep
from corm.models import Community, Source, Member, Contact, Channel, Conversation
from corm.connectors import ConnectionManager

class Command(BaseCommand):
    help = 'Import data from sources'

    def add_arguments(self, parser):
        parser.add_argument('importer', type=str)
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--source', dest='source_id', type=int)
        parser.add_argument('--channel', dest='channel_id', type=int)
        parser.add_argument('--full', dest='full_import', action='store_true', help='Do a full import, not incremental from the previous import')
        parser.add_argument('--new', dest='new_only', action='store_true', help='Import only from new sources')
        parser.add_argument('--debug', dest='debug', action='store_true', help='Enter debugger on errors')
        parser.add_argument('--limit', dest='limit', type=int, help='Number of possible sources to import')

    def handle(self, *args, **options):

        importer_name = options.get('importer')
        verbosity = options.get('verbosity')
        community_id = options.get('community_id')
        source_id = options.get('source_id')
        channel_id = options.get('channel_id')
        full_import = options.get('full_import')
        new_only = options.get('new_only')
        debug = options.get('debug')
        limit = options.get('limit')

        if importer_name == 'all':
            verbosity and print("Importing all sources")
            sources = Source.objects.filter(community__status=Community.ACTIVE, enabled=True).exclude(connector='corm.plugins.api')
        elif importer_name is not None and importer_name in ConnectionManager.CONNECTOR_IMPORTERS:
            verbosity and print("Importing %s data" % importer_name)
            plugin = ConnectionManager.CONNECTOR_IMPORTERS[importer_name]
            sources = Source.objects.filter(connector=plugin.__module__, enabled=True, community__status=Community.ACTIVE)
        else:
            print("Unknown import target: %s" % importer_name)
            print("Available importers are: %s" % ", ".join(ConnectionManager.CONNECTOR_IMPORTERS.keys()))
            return False

        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            sources = sources.filter(community=community)

        if source_id:
            source = Source.objects.get(id=source_id)
            print("Using Source: %s" % source.name)
            sources = sources.filter(id=source.id)

        if channel_id:
            channels = Channel.objects.filter(id=channel_id)
            print("Using Channel: %s" % channels[0].name)
            sources = sources.filter(id=channels[0].source_id)
        else:
            channels = None

        if new_only:
            print("Using new sources only")
            sources = sources.filter(first_import__isnull=True)

        if limit:
            sources = sources[:limit]

        for source in sources:
            print("Importing %s" % source)
            if new_only:
                source.first_import = datetime.datetime.utcnow()
                source.save()
            try:
                plugin = ConnectionManager.CONNECTOR_PLUGINS[source.connector]
                importer = plugin.get_source_importer(source)
                importer.verbosity = verbosity
                importer.debug = debug
                importer.full_import = full_import
            except Exception as e:
                print("Failed to import Source %s: %s" % (source, e))
                if new_only:
                    source.first_import = None
                    source.save()
                continue

            try:
                if verbosity >= 2:
                    print("Importing %s source: %s" % (plugin.get_source_type_name(), source))
                importer.run(new_only, channels=channels)
                if full_import:
                    sleep(5)
            except Exception as e:
                print(e)
                if new_only:
                    source.first_import = None
                    source.save()
