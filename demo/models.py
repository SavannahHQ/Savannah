from django.db import models
from corm.models import Community

# Create your models here.
class Demonstration(models.Model):
    SEED = 0
    READY = 1
    IN_USE = 2

    STATUS_CHOICES = [
        (SEED, 'Seed'),
        (READY, 'Ready'),
        (IN_USE, 'In Use'),
    ]
    STATUS_NAMES = {
        SEED: "Seed",
        READY: "Ready",
        IN_USE: "In Use",
    }
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    status = models.SmallIntegerField(choices=STATUS_CHOICES, default=SEED)
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(blank=True, null=True)

