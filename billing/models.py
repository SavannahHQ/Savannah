from django.db import models

from django.contrib.auth.models import User, Group
from corm.models import Community

from djstripe.models import Customer, Subscription
# Create your models here.
class Company(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    communities = models.ManyToManyField(Community, through='Management')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="The team's Stripe Subscription object, if it exists"
    )

    def __str__(self):
        return self.name

class Management(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="The team's Stripe Subscription object, if it exists"
    )

    def __str__(self):
        return "%s/%s" % (self.company.name, self.community.name)

