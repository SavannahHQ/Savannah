import datetime
from django.db import models
from django.contrib.auth.models import User, Group
from corm.models import Community

# Create your models here.
class DemoLog(models.Model):
    name = models.CharField(max_length=256)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField()
    deleted_at = models.DateTimeField(null=True, blank=True)
    managers = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True)
    
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
    log = models.ForeignKey(DemoLog, on_delete=models.SET_NULL, null=True, blank=True)

    def delete(self, *args, **kwargs):
        if self.log is not None:
            self.log.deleted_at = datetime.datetime.utcnow()
            self.log.save()
        if self.community is not None:
            self.community.delete()
        return super(Demonstration, self).delete(*args, **kwargs)

    def __str__(self):
        if self.community:
            return "Demonstration object (%s)" % self.community.name
        return "Demonstration object (%s)" % self.id