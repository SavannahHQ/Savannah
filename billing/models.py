from django.db import models
from django.conf import settings
from django.contrib.auth.models import User, Group
from corm.models import Community, ManagementPermissionMixin

from djstripe.models import Customer, Subscription
# Create your models here.
class Organization(models.Model):
    name = models.CharField(verbose_name="Company/Organization Name", max_length=100)
    email = models.EmailField(verbose_name="Contact Email Address")
    communities = models.ManyToManyField(Community, through='Management')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="The team's Stripe Customer object, if it exists"
    )

    def __str__(self):
        return self.name

class Management(models.Model, ManagementPermissionMixin):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    community = models.OneToOneField(Community, related_name='_management', on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="The team's Stripe Subscription object, if it exists"
    )

    @property
    def metadata(self):
        if not hasattr(self, '_metadata'):
            if self.subscription is not None:
                self._metadata = self.subscription.plan.metadata or {}
            else:
                self._metadata = {'name': 'No Plan'}
        return self._metadata

    def __str__(self):
        return "%s/%s" % (self.org.name, self.community.name)

    def subscribe(self, subscription_id):
        try:
            subscription = Subscription.objects.get(id=subscription_id)
            self.subscription = subscription
            self.save()
            self.community.status = Community.ACTIVE
            self.community.save()
        except Exception as e:
            raise Exception("Failed to subscribe '%s' to %s: %s" % (self.community.name, subscription_id, e))

    @classmethod
    def unsubscribe(self, subscription_id):
        try:
            management = Management.objects.get(subscription__id=subscription_id)
            management.community.status = Community.DEACTIVE
            management.community.save()
        except Exception as e:
            raise Exception("Failed to unsubscribe %s: %s" % (subscription_id, e))

    def can_change_to(self, plan):
        plan_data = plan.metadata

        managers = int(plan_data.get('managers', 0))
        if managers > 0 and self.community.managers.user_set.all().count() > managers:
            return False

        sources = int(plan_data.get('sources', 0))
        if sources > 0 and self.community.source_set.all().count() > sources:
            return False

        tags = int(plan_data.get('tags', 0))
        if tags > 0 and self.community.tag_set.all().count() > tags:
            return False

        projects = int(plan_data.get('projects', 0))
        if projects > 0 and self.community.project_set.filter(default_project=False).count() > projects:
            return False

        return True

    @classmethod
    def suspend(self, subscription_id):
        try:
            management = Management.objects.get(subscription__id=subscription_id)
            management.community.status = Community.SUSPENDED
            management.community.save()
        except Exception as e:
            raise Exception("Failed to suspend %s: %s" % (subscription_id, e))

    @property
    def name(self):
        if 'name' in self.metadata:
            return self.metadata.get('name')
        elif self.subscription is not None:
            return self.subscription.plan.nickname
        else:
            return "None"

    @property
    def managers(self):
        return int(self.metadata.get('managers', 0))

    @property
    def sources(self):
        return int(self.metadata.get('sources', 0))

    @property
    def tags(self):
        return int(self.metadata.get('tags', 0))

    @property
    def projects(self):
        return int(self.metadata.get('projects', 0))

    @property
    def import_days(self):
        return int(self.metadata.get('import_days', 0))

    @property
    def retention_days(self):
        return int(self.metadata.get('retention_days', 0))

    @property
    def sales_itegration(self):
        return bool(self.metadata.get('sales_itegration', False))

