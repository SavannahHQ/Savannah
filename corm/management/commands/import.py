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

    def handle(self, *args, **options):

      importer_name = options.get('importer')
      if importer_name in ConnectionManager.CONNECTOR_IMPORTERS:
        print("Importing %s data" % importer_name)
        plugin = ConnectionManager.CONNECTOR_IMPORTERS[importer_name]

        for source in Source.objects.filter(connector=plugin.__module__, auth_secret__isnull=False):
          importer = plugin.get_source_importer(source)
          importer.run()
      else:
          print("Unknown importer: %s" % importer_name)
          print("Available importers are: %s" % ", ".join(ConnectionManager.CONNECTOR_IMPORTERS.keys()))
