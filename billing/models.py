from django.db import models

from django.contrib.auth.models import User, Group
from corm.models import Community

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

class Management(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="The team's Stripe Subscription object, if it exists"
    )

    def __str__(self):
        return "%s/%s" % (self.org.name, self.community.name)

    def subscribe(self, subscription_id):
        try:
            subscription_id = int(subscription_id)
            subscription = Subscription.objects.get(id=subscription_id)
            self.subscription = subscription
            self.save()
            self.community.status = Community.ACTIVE
            self.community.save()
        except:
            raise Exception("Failed to subscribe %s: Unknown Stripe plan: %s" % (self.community.name, subscription_id))