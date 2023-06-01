from django.db import models
from django.conf import settings
from django.contrib.auth.models import User, Group
from corm.models import Community, ManagementPermissionMixin
from jsonfield.fields import JSONField

from djstripe.models import Customer, Subscription
from djstripe.enums import SubscriptionStatus
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
    overrides = JSONField(null=True, blank=True)

    @property 
    def is_billable(self):
        if self.subscription is None:
            return False
        if self.subscription.status == SubscriptionStatus.canceled:
            return False
        if self.subscription.plan is None:
            return False
        return True

    @property
    def is_per_seat(self):
        return self.subscription is not None and self.subscription.plan is not None and self.subscription.plan.billing_scheme == 'tiered'

    @property
    def billable_seats(self):
        seats = self.community.managers.user_set.all().count()
        return seats

    @property
    def monthly_invoice_url(self):
        try:
            invoice = self.subscription.invoices.all().order_by('-period_end').first()
            return invoice.hosted_invoice_url
        except:
            return None

    @property
    def monthly_cost(self):
        print("Monthly cost")
        try:
            invoice = self.subscription.invoices.all().order_by('-period_end').first()
            return invoice.total
        except:
            # Fallback to calculating the expected monthly cost
            pass
        try:
            plan = self.subscription.plan
            if self.is_per_seat:
                manager_count = self.billable_seats
                tier_start = 0
                amount = 0
                for tier in plan.tiers:
                    if tier["up_to"] is None:
                        tier["up_to"] = 10000
                    if manager_count > tier_start:
                        if tier["flat_amount"] is not None:
                            amount += tier["flat_amount"]
                        if tier["unit_amount"] is not None:
                            amount += (tier["unit_amount"] * min(manager_count - tier_start, tier["up_to"]))
                        tier_start = tier["up_to"]
                return amount / 100
            else:
                return plan.amount
        except Exception as e:
            print(e)
            return 0
    @property
    def metadata(self):
        if not hasattr(self, '_metadata'):
            if self.subscription is not None:
                self._metadata = self.subscription.plan.metadata or {}
                if self.overrides is not None:
                    self._metadata.update(self.overrides)
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

    def update(self, **kwargs):
        if self.subscription is not None:
            if self.subscription.status in ['canceled', 'incomplete_expired']:
                return
            if 'plan' in kwargs:
                self.subscription.plan = kwargs['plan']
            quantity = 1
            if self.is_per_seat:
                quantity = self.billable_seats
            kwargs['quantity'] = quantity
            self.subscription.update(**kwargs)

    def can_change_to(self, plan):
        plan_data = plan.metadata
        override_data = self.overrides or {}

        managers = int(plan_data.get('managers', 0))
        if managers > 0 and self.community.managers.user_set.all().count() > managers:
            return False

        sources = int(plan_data.get('sources', 0))
        if sources > 0 and self.community.source_set.filter(enabled=True).exclude(connector='corm.plugins.null').count() > sources:
            return False

        tags = int(plan_data.get('tags', 0))
        if tags > 0 and self.community.tag_set.all().count() > tags:
            return False

        projects = int(plan_data.get('projects', 0))
        if projects > 0 and self.community.project_set.filter(default_project=False).count() > projects:
            return False

        can_have_sales = override_data.get('sales_integration', plan_data.get('sales_integration', False))
        if not can_have_sales and self.community.source_set.filter(connector='corm.plugins.salesforce').count() > 0:
            print("Can't change due to sales integration")
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
        return self.metadata.get('sales_integration', '').lower() in ['1', 't', 'true', 'yes']

