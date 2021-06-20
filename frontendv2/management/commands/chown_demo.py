from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from corm.models import Community, MemberWatch, Task, ManagerProfile


class Command(BaseCommand):
    help = 'Generate a Community with mock data'

    def add_arguments(self, parser):
        parser.add_argument('--community', type=int)
        parser.add_argument('--owner', type=str)
        parser.add_argument('--owner_id', type=int)


    def handle(self, *args, **options):
        community_id = options.get("community")
        owner_name = options.get("owner")
        owner_id = options.get("owner_id")

        try:
            if community_id:
                community = Community.objects.get(id=community_id)
            else:
                print("You must supply a --owner or --owner_id")
                exit(1)

            if owner_id:
                owner = User.objects.get(id=owner_id)
            elif owner_name:
                owner = User.objects.get(username=owner_name)
            else:
                print("You must supply a --owner or --owner_id")
                exit(1)
        except Exception as e:
            print(e)
            exit(1)

        prev_owner = community.owner
        community.owner = owner
        community.save()

        ManagerProfile.objects.filter(community=community, user=prev_owner).update(user=owner)
        MemberWatch.objects.filter(member__community=community, manager=prev_owner).update(manager=owner)
        Task.objects.filter(community=community, owner=prev_owner).update(owner=owner)
        