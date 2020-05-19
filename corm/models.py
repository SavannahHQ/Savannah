import datetime
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
    class Meta:
        ordering = ("name",)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    color = models.CharField(max_length=16)
    keywords = models.CharField(max_length=256, null=True, blank=True, help_text=_("Comma-separated list of words. If found in a conversation, this tag will be applied."))

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class TaggableModel(models.Model):
    class Meta:
        abstract = True
    tags = models.ManyToManyField(Tag, blank=True)

class ImportedDataModel(models.Model):
    class Meta:
        abstract = True
    origin_id = models.CharField(max_length=256, null=True, blank=True, unique=False)

class MemberConnection(models.Model):
    class Meta:
        ordering = ("-first_connected",)
    from_member = models.ForeignKey('Member', on_delete=models.CASCADE)
    to_member = models.ForeignKey('Member', on_delete=models.CASCADE, related_name='connectors')
    via = models.ForeignKey('Source', on_delete=models.SET_NULL, null=True)
    first_connected = models.DateTimeField(db_index=True)
    last_connected = models.DateTimeField(db_index=True)
    
    def __str__(self):
        return "%s -> %s" % (self.from_member, self.to_member)

class Member(TaggableModel):
    class Meta:
        ordering = ("name",)
        unique_together = [["community", "user"]]
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=256, db_index=True)
    first_seen = models.DateTimeField(auto_now_add=False, db_index=True)
    last_seen = models.DateTimeField(db_index=True, null=True, blank=True)

    email_address = models.EmailField(null=True, blank=True)
    mailing_address = models.CharField(max_length=256, null=True, blank=True)
    phone_number = models.CharField(max_length=32, null=True, blank=True)
    avatar_url = models.URLField(null=True, blank=True)

    connections = models.ManyToManyField('Member', through='MemberConnection')

    def is_connected(self, other):
        return MemberConnection.objects.filter(from_member=self, to_member=other).count() > 0

    def add_connection(self, other, source, timestamp=None):
        if self.id == other.id:
            return
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
        return self.name

    def merge_with(self, other_member):
        if self.user is None and other_member.user is not None :
            self.user = other_member.user
        if other_member.first_seen is not None and (self.first_seen is None or self.first_seen > other_member.first_seen):
            self.first_seen = other_member.first_seen
        if other_member.last_seen is not None and (self.last_seen is None or self.last_seen < other_member.last_seen):
            self.last_seen = other_member.last_seen
        Contact.objects.filter(member=other_member).update(member=self)
        Note.objects.filter(member=other_member).update(member=self)
        MemberConnection.objects.filter(from_member=other_member).update(from_member=self)
        MemberConnection.objects.filter(to_member=other_member).update(to_member=self)
        Contribution.objects.filter(author=other_member).update(author=self)

        for tag in other_member.tags.all():
            self.tags.add(tag)

        Conversation.objects.filter(speaker=other_member).update(speaker=self)
        for convo in Conversation.objects.filter(participants=other_member):
            convo.participants.add(self)
            convo.participants.remove(other_member)

        for task in Task.objects.filter(stakeholders=other_member):
            task.stakeholders.add(self)
            task.stakeholders.remove(other_member)

        for project in Project.objects.filter(collaborators=other_member):
            project.collaborators.add(self)
            project.collaborators.remove(other_member)

        self.save()
        other_member.delete()

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
    last_import = models.DateTimeField(null=True, blank=True)

    @property
    def activity_set(self):
        return Contribution.objects.filter(contribution_type__source=self)

    @property
    def conversation_set(self):
        return Conversation.objects.filter(channel__source=self)

    @property
    def has_engagement(self):
        return (self.activity_set.count() + self.conversation_set.count()) > 0

    def __str__(self):
        return self.name

class Channel(ImportedDataModel):
    class Meta:
        ordering = ("name",)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)
    last_import = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

class Contact(ImportedDataModel):
    class Meta:
        ordering = ("detail",)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    detail = models.CharField(max_length=256)
    email_address = models.EmailField(null=True, blank=True)
    avatar_url = models.URLField(null=True, blank=True)

    @property
    def link_url(self):
        if hasattr(self, '_identity_url'):
            return self._identity_url
        else:
            self._identity_url = ConnectionManager.get_identity_url(self)
            return self._identity_url

    def __str__(self):
        return "%s (%s)" % (self.detail, self.source.name)

class Conversation(TaggableModel, ImportedDataModel):
    class Meta:
        ordering = ("-timestamp",)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    speaker = models.ForeignKey(Member, related_name='speaker_in', on_delete=models.SET_NULL, null=True, blank=True)
    participants = models.ManyToManyField(Member)
    content = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    location = models.URLField(max_length=512, null=True, blank=True)
    thread_start = models.ForeignKey('Conversation', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        if self.content is not None and len(self.content) > 2:
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
    owner = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=256)
    detail = models.TextField()
    due = models.DateTimeField()
    done = models.DateTimeField(null=True, blank=True, db_index=True)
    stakeholders = models.ManyToManyField(Member)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def is_done(self):
        return self.done is not None

    def __str__(self):
        return self.name

class ContributionType(models.Model):
    class Meta:
        verbose_name = _("Contribution Type")
        verbose_name_plural = _("Contribution Types")
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=256)
    feed = models.URLField(null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

class Contribution(TaggableModel, ImportedDataModel):
    class Meta:
        verbose_name_plural = _("Contributions")
        ordering = ('-timestamp',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    contribution_type = models.ForeignKey(ContributionType, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=256)
    timestamp = models.DateTimeField(db_index=True)
    author = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    location = models.URLField(null=True, blank=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True)

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

class Suggestion(models.Model):
    class Meta:
        abstract = True
    REJECTED = -1
    IGNORED = 0
    ACCEPTED = 1
    ACTION_STATUS = [
        (ACCEPTED, 'Accepted'),
        (IGNORED, 'Ignored'),
        (REJECTED, 'Rejected'),
    ]
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    reason = models.CharField(max_length=256, null=True, blank=True)
    status = models.SmallIntegerField(choices=ACTION_STATUS, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    actioned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    actioned_at = models.DateTimeField(null=True, blank=True)

    def accept_action(self):
        raise NotImplementedError

    def act_on_suggestion(self, user, action):
        self.actioned_at = datetime.datetime.utcnow()
        self.actioned_by = user
        self.status = action
        self.save()

    def accept(self, user):
        update_suggestion = self.accept_action()
        if update_suggestion is not False:
            self.act_on_suggestion(user, Suggestion.ACCEPTED)

    def reject(self, user):
        self.act_on_suggestion(user, Suggestion.REJECTED)

    def ignore(self, user):
        self.act_on_suggestion(user, Suggestion.IGNORED)

class SuggestMemberMerge(Suggestion):
    source_member = models.ForeignKey(Member, related_name='merge_to_suggestions', on_delete=models.CASCADE)    
    destination_member = models.ForeignKey(Member, related_name='merge_with_suggestions', on_delete=models.CASCADE)

    def accept_action(self):
        self.destination_member.merge_with(self.source_member)
        return False

class SuggestMemberTag(Suggestion):
    target_member = models.ForeignKey(MemberConnection, related_name='tag_suggestions', on_delete=models.CASCADE)    
    suggested_tag = models.ForeignKey(Tag, related_name='member_suggestions', on_delete=models.CASCADE)

    def accept_action(self):
        self.target_member.tags.add(self.suggested_tag)

class SuggestConversationTag(Suggestion):
    target_conversation = models.ForeignKey(Conversation, related_name='tag_suggestions', on_delete=models.CASCADE)    
    suggested_tag = models.ForeignKey(Tag, related_name='conversation_suggestions', on_delete=models.CASCADE)

    def accept_action(self):
        self.target_conversation.tags.add(self.suggested_tag)

def pluralize(count, singular, plural=None):
    if plural is None:
        plural = singular + "s"
    try:
        count = int(count)
        if count != 1:
            return plural
    except:
        pass
    return singular