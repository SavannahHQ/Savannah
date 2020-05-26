from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import string
from django.contrib.auth.models import User, Group
from corm.models import Community, Tag

class Command(BaseCommand):
    help = 'Auto-Connect participants in conversations'

    def add_arguments(self, parser):
        parser.add_argument('name', type=str)
        parser.add_argument('--owner_id', type=int)


    def handle(self, *args, **options):
        community_name = options.get('name')
        print("Creating new community: %s" % community_name)

        owner_id = options.get('owner_id')
        if owner_id:
            owner = User.objects.get(id=owner_id)
        else:
            owner = User.objects.filter(is_staff=True).order_by('id')[0]

        managers = Group.objects.create(name="%s Managers" % community_name)
        owner.groups.add(managers)
        community = Community.objects.create(name=community_name, owner=owner, managers=managers, icon_path='/static/savannah/Savannah32.png')

        thankful = Tag.objects.create(name="thankful", community=community, color="aff5ab", keywords="thanks, thank you, thx, thank yo")
        greeting = Tag.objects.create(name="greeting", community=community, color="abdef5", keywords="welcome, hi, hello")
