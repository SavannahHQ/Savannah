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
                self._metadata = settings.STRIPE_PLANS.get(self.subscription.plan.id, {})
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

    @classmethod
    def suspend(self, subscription_id):
        try:
            management = Management.objects.get(subscription__id=subscription_id)
            management.community.status = Community.SUSPENDED
            management.community.save()
        except Exception as e:
            raise Exception("Failed to suspend %s: %s" % (subscription_id, e))

    def can_add_manager(self):
        if self.metadata.get('managers', 0) > 0:
            print('Limit: %s Managers' % self.metadata.get('managers', 0))
            return self.community.managers.user_set.all().count() < self.metadata.get('managers', 0)
        else:
            print('Unlimited Managers')
            return True

    def can_add_source(self):
        if self.metadata.get('sources', 0) > 0:
            return self.community.source_set.all().count() < self.metadata.get('sources', 0)
        else:
            return True

    def can_add_tag(self):
        if self.metadata.get('tags', 0) > 0:
            return self.community.tag_set.all().count() < self.metadata.get('tags', 0)
        else:
            return True

    def can_add_project(self):
        if self.metadata.get('projects', 0) > 0:
            return self.community.project_set.filter(default_project=False).count() < self.metadata.get('projects', 0)
        else:
            return True

    def max_import_date(self):
        if self.metadata.get('import_days', 0) > 0:
            return self.community.created - datetime.timedelta(days=self.metadata.get('import_days', 0))
        else:
            return self.community.created - datetime.timedelta(years=5)

    def max_retention_date(self):
        if self.metadata.get('retention_days', 0) > 0:
            return datetime.datetime.utcnow() - datetime.timedelta(days=self.metadata.get('retention_days', 0))
        else:
            return self.community.created - datetime.timedelta(years=3)
