from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from perceval.backends.core.slack import Slack
from corm.models import Contact, Community, Source, ConnectionManager

class Command(BaseCommand):
    help = 'Import Identity details from their Source'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--source', dest='source_id', type=int)
        parser.add_argument('--connector', dest='connector', type=str)

    def handle(self, *args, **options):

      identities = Contact.objects.all()
      verbosity = options.get('verbosity')

      community_id = options.get('community_id')
      source_id = options.get('source_id')
      connector = options.get('connector')

      if community_id:
          community = Community.objects.get(id=community_id)
          print("Using Community: %s" % community.name)
          identities = identities.filter(source__community=community)

      if source_id:
          source = Source.objects.get(id=source_id)
          print("Using Source: %s" % source.name)
          identities = identities.filter(source=source)

      if connector:
          print("Using Connector: %s" % ConnectionManager.display_name(connector))
          identities = identities.filter(source__connector=connector)

      print("Updating info from %s identities" % identities.count())
      importer_cache = {}
      for ident in identities:
          if ident.source.connector not in ConnectionManager.CONNECTOR_PLUGINS:
            continue

          if ident.source.id in importer_cache:
              importer = importer_cache[ident.source.id]
          else:
              plugin = ConnectionManager.CONNECTOR_PLUGINS[ident.source.connector]
              importer = plugin.get_source_importer(ident.source)
              importer.verbosity = verbosity
              importer_cache[ident.source.id] = importer
          importer.update_identity(ident)