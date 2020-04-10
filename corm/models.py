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
    icon_path = models.CharField(max_length=256)

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

class ImportedDataModel(models.Model):
    class Meta:
        abstract = True
    origin_id = models.CharField(max_length=256, null=True, blank=True, unique=True)

class MemberConnection(models.Model):
    class Meta:
        ordering = ("-last_connected",)
    from_member = models.ForeignKey('Member', on_delete=models.CASCADE)
    to_member = models.ForeignKey('Member', on_delete=models.CASCADE, related_name='connectors')
    via = models.ForeignKey('Source', on_delete=models.SET_NULL, null=True)
    first_connected = models.DateTimeField()
    last_connected = models.DateTimeField()
    
    def __str__(self):
        return "%s -> %s" % (self.from_member, self.to_member)

class Member(TaggableModel):
    class Meta:
        ordering = ("name",)
        unique_together = [["community", "user"]]
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=256)
    date_added = models.DateTimeField(auto_now_add=True)

    connections = models.ManyToManyField('Member', through='MemberConnection')

    def is_connected(self, other):
        return MemberConnection.objects.filter(from_member=self, to_member=other).count() > 0

    def add_connection(self, other, source, timestamp=None):
        if self.is_connected(other):
            MemberConnection.objects.filter(from_member=self, to_member=other).update(last_connected=timestamp)
            MemberConnection.objects.filter(from_member=other, to_member=self).update(last_connected=timestamp)
        else:              
            MemberConnection.objects.create(from_member=self, to_member=other, via=source, first_connected=timestamp, last_connected=timestamp)
            MemberConnection.objects.create(from_member=other, to_member=self, via=source, first_connected=timestamp, last_connected=timestamp)
        
    def remove_connection(self, other):
        MemberConnection.objects.filter(from_member=self, to_member=other).delete()
        MemberConnection.objects.filter(from_member=other, to_member=self).delete()
        
    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Project(models.Model):
    class Meta:
        ordering = ("name",)
    name = models.CharField(max_length=256)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    collaborators = models.ManyToManyField(Member)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Source(models.Model):
    class Meta:
        ordering = ("name",)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    connector = models.CharField(max_length=256, choices=ConnectionManager.CONNECTOR_CHOICES)
    name = models.CharField(max_length=256)
    server = models.CharField(max_length=256, null=True, blank=True)
    auth_id = models.CharField(max_length=256, null=True, blank=True)
    auth_secret = models.CharField(max_length=256, null=True, blank=True)
    icon_name = models.CharField(max_length=256, null=True, blank=True)

    @property
    def activity_set(self):
        return Activity.objects.filter(activity_type__source=self)

    @property
    def conversation_set(self):
        return Conversation.objects.filter(channel__source=self)

    @property
    def has_engagement(self):
        return (self.activity_set.count() + self.conversation_set.count()) > 0

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Channel(ImportedDataModel):
    class Meta:
        ordering = ("name",)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)

    def __str__(self):
        return "%s: %s (%s)" % (self.source.name, self.name, self.source.community)

class Contact(ImportedDataModel):
    class Meta:
        ordering = ("detail",)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    detail = models.CharField(max_length=256)

    def __str__(self):
        return "%s (%s)" % (self.detail, self.source.name)

class Conversation(TaggableModel, ImportedDataModel):
    class Meta:
        ordering = ("-timestamp",)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    participants = models.ManyToManyField(Member)
    content = models.TextField()
    timestamp = models.DateTimeField()
    location = models.URLField(null=True, blank=True)

    def __str__(self):
        if len(self.content) > 2:
            try:
                return self.content[:min(self.content.index('\n'), 64)]
            except:
                return self.content[:min(len(self.content), 64)]
        else:
            return str(self.timestamp)

class Task(TaggableModel):
    class Meta:
        ordering = ("done", "due",)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    detail = models.TextField()
    due = models.DateTimeField()
    done = models.DateTimeField(null=True, blank=True)
    stakeholders = models.ManyToManyField(Member)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True)

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

class Activity(TaggableModel, ImportedDataModel):
    class Meta:
        verbose_name_plural = _("Activity")
        ordering = ('timestamp',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE)
    title = models.CharField(max_length=256)
    timestamp = models.DateTimeField()
    author = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    location = models.URLField(null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.title, self.community)

class Note(TaggableModel):
    class Meta:
        ordering = ("-timestamp",)
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