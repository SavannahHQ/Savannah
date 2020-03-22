from django.db import models
from django.contrib.auth.models import User, Group

from django.utils.translation import ugettext_lazy as _

from corm.connectors import ConnectionManager

# Create your models here.

class Community(models.Model):
    class Meta:
        verbose_name = _("Community")
        verbose_name_plural = _("Communities")
    name = models.CharField(max_length=256)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    managers = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.name

class Tag(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    color = models.CharField(max_length=16)
    icon = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class TaggableModel(models.Model):
    class Meta:
        abstract = True
    tags = models.ManyToManyField(Tag, blank=True)

class Member(TaggableModel):
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=256)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Project(TaggableModel):
    name = models.CharField(max_length=256)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    collaborators = models.ManyToManyField(Member)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Source(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    connector = models.CharField(max_length=256, choices=ConnectionManager.CONNECTOR_CHOICES)
    name = models.CharField(max_length=256)
    server = models.CharField(max_length=256, null=True, blank=True)
    auth_id = models.CharField(max_length=256, null=True, blank=True)
    auth_secret = models.CharField(max_length=256, null=True, blank=True)
    icon_name = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Channel(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)

    def __str__(self):
        return "%s: %s (%s)" % (self.source.name, self.name, self.source.community)

class Contact(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    detail = models.CharField(max_length=256)

    def __str__(self):
        return "%s (%s)" % (self.detail, self.source.name)

class Conversation(TaggableModel):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    participants = models.ManyToManyField(Member)
    content = models.TextField()
    timestamp = models.DateTimeField()
    location = models.URLField(null=True, blank=True)

    def __str__(self):
        if len(self.content) > 2:
            try:
                return self.content[:self.content.index('\n')]
            except:
                return self.content[:min(len(self.content), 32)]
        else:
            return str(self.timestamp)

class Task(TaggableModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    detail = models.TextField()
    due = models.DateTimeField()
    done = models.DateTimeField(null=True, blank=True)
    stakeholders = models.ManyToManyField(Member)

    @property
    def is_done(self):
        return self.done is not None

    def __str__(self):
        return self.name

class ActivityType(models.Model):
    class Meta:
        verbose_name = _("Activity Type")
        verbose_name_plural = _("Activity Types")
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=256)
    feed = models.URLField(null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Activity(TaggableModel):
    class Meta:
        verbose_name_plural = _("Activity")
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE)
    title = models.CharField(max_length=256)
    timestamp = models.DateTimeField()
    author = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    location = models.URLField(null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.title, self.community)

class Note(TaggableModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    content = models.TextField()

    def __str__(self):
        if len(self.content) > 2:
            try:
                return self.content[:self.content.index('\n')]
            except:
                return self.content[:min(len(self.content), 32)]
        else:
            return str(self.timestamp)