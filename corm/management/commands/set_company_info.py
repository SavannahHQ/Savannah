from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from corm.models import *

class Command(BaseCommand):
    help = "Set a member's company basesd on imported data"

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)

    def handle(self, *args, **options):

      verbosity = options.get('verbosity')

      community_id = options.get('community_id')

      domain_cache = dict()
      if community_id:
          communities = [Community.objects.get(id=community_id)]
      else:
          communities = Community.objects.filter(status=Community.ACTIVE)

      for community in communities:
        members = Member.objects.filter(community=community, company__isnull=True)
        print("Updating info from %s members in %s" % (members.count(), community))
        domain_cache = dict([(d.domain, d.company) for d in CompanyDomains.objects.filter(company__community=community)])

        for member in members:
            # Assign company based on email domain matching
            if member.email_address is not None:
                try:
                    (identity, domain) = member.email_address.split('@', maxsplit=1)
                except:
                    # Failed to identify domain component of the email address
                    continue
                if domain not in domain_cache:
                    # Domain doesn't belong to a defined company
                    continue
                company = domain_cache[domain]
                member.company = company
                member.save()

        # Ensure that all members with a company have their role and tag set
        for member in Member.objects.filter(community=community, company__isnull=False):
            if member.company.is_staff:
                member.role = Member.STAFF
                member.save()
            if member.company.tag:
                member.tags.add(member.company.tag)
