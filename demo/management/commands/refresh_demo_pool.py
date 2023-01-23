import datetime
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.db.models import Min
from django.conf import settings

from corm.models import Community
from demo.models import Demonstration

class Command(BaseCommand):
    help = 'Create and seed demo communities up to settings.DEMO_POOL limit'


    def handle(self, *args, **options):
        for demo in Demonstration.objects.filter(expires__lte=datetime.datetime.utcnow()):
            # demo.community.delete()
            demo.community.webhook_set.all().delete()
            demo.delete()

        pool_size = Demonstration.objects.filter(status=Demonstration.READY).count()
        while pool_size < settings.DEMO_POOL:
            system_user = User.objects.get(username=settings.SYSTEM_USER)
            try:
                demo = Demonstration.objects.filter(status=Demonstration.SEED).order_by('created')[0]
            except:
                new_community = Community.objects.create(name='Pool Demo', owner=system_user)
                demo = Demonstration.objects.create(community=new_community)

            call_command('make_demo', community_id=demo.community.id, name='Pool', owner_id=system_user.id, size=settings.DEMO_SIZE)
            demo.expires = datetime.datetime.utcnow() + datetime.timedelta(hours=settings.DEMO_DURATION_HOURS)
            demo.status = demo.READY
            demo.save()
            pool_size += 1