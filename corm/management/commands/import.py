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
        parser.add_argument('--full', dest='full_import', action='store_true', help='Do a full import, not incremental from the previous import')

    def handle(self, *args, **options):

      importer_name = options.get('importer')
      verbosity = options.get('verbosity')
      community_id = options.get('community_id')
      source_id = options.get('source_id')
      full_import = options.get('full_import')

      if importer_name in ConnectionManager.CONNECTOR_IMPORTERS:
        verbosity and print("Importing %s data" % importer_name)
        plugin = ConnectionManager.CONNECTOR_IMPORTERS[importer_name]

        sources = Source.objects.filter(connector=plugin.__module__, enabled=True)
        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            sources = sources.filter(community=community)

        if source_id:
            source = Source.objects.get(id=source_id)
            print("Using Source: %s" % source.name)
            sources = sources.filter(id=source.id)

        for source in sources:
          importer = plugin.get_source_importer(source)
          importer.verbosity = verbosity
          importer.full_import = full_import
          importer.run()
      else:
          print("Unknown importer: %s" % importer_name)
          print("Available importers are: %s" % ", ".join(ConnectionManager.CONNECTOR_IMPORTERS.keys()))
