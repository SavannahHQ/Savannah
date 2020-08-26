import datetime
from django.db import models
from django.contrib.auth.models import User, Group
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.contrib.messages.constants import DEFAULT_TAGS, WARNING

from imagekit import ImageSpec
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

from corm.connectors import ConnectionManager

class Icon(ImageSpec):
    processors = [ResizeToFill(32, 32)]
    format = 'PNG'

    
    # Create your models here.

class UserAuthCredentials(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    connector = models.CharField(max_length=256, choices=ConnectionManager.CONNECTOR_CHOICES)
    server = models.CharField(max_length=256, null=True, blank=True)
    auth_id = models.CharField(max_length=256, null=True, blank=True)
    auth_secret = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return "%s on %s" % (self.user, ConnectionManager.display_name(self.connector))

class Community(models.Model):
    class Meta:
        verbose_name = _("Community")
        verbose_name_plural = _("Communities")
        ordering = ("name",)
    name = models.CharField(verbose_name="Community Name", max_length=256)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    managers = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    logo = models.ImageField(upload_to='community_logos', null=True)
    icon = ImageSpecField(source='logo', spec=Icon)

    @property
    def default_project(self):
        return Project.objects.get(community=self, default_project=True)

    @property
    def icon_path(self):
        try:
            return self.icon.url
        except:
            return "%ssavannah/Savannah32.png" % settings.STATIC_URL

    def bootstrap(self):
        if self.managers is None:
            self.managers = Group.objects.create(name="%s Managers (%s)" % (self.name, self.id))
            self.owner.groups.add(self.managers)
            self.save()
        Tag.objects.get_or_create(name="thankful", community=self, defaults={'color':"aff5ab", 'keywords':"thanks, thank you, thx, thank yo"})
        Tag.objects.get_or_create(name="greeting", community=self, defaults={'color':"abdef5", 'keywords':"welcome, hi, hello"})
        Project.objects.get_or_create(community=self, default_project=True, defaults={'name': self.name, 'owner':None, 'threshold_user':1, 'threshold_participant':10, 'threshold_contributor':1, 'threshold_core':10})
            
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
    COMMUNITY = "community"
    STAFF = "staff"
    BOT = "bot"
    MEMBER_ROLE = [
        (COMMUNITY, 'Community'),
        (STAFF, 'Staff'),
        (BOT, 'Bot'),
    ]
    ROLE_NAME = {
        COMMUNITY: "Community",
        STAFF: "Staff",
        BOT: "Bot"
    }
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
    role = models.CharField(max_length=32, choices=MEMBER_ROLE, default=COMMUNITY)

    connections = models.ManyToManyField('Member', through='MemberConnection')

    def is_connected(self, other):
        return MemberConnection.objects.filter(from_member=self, to_member=other).count() > 0

    def add_connection(self, other, source, timestamp=None):
        if self.id == other.id:
            return
        if self.is_connected(other):
            MemberConnection.objects.filter(from_member=self, to_member=other, last_connected__lt=timestamp).update(last_connected=timestamp)
            MemberConnection.objects.filter(from_member=other, to_member=self, last_connected__lt=timestamp).update(last_connected=timestamp)
        else:              
            MemberConnection.objects.create(from_member=self, to_member=other, via=source, first_connected=timestamp, last_connected=timestamp)
            MemberConnection.objects.create(from_member=other, to_member=self, via=source, first_connected=timestamp, last_connected=timestamp)
        
    def remove_connection(self, other):
        MemberConnection.objects.filter(from_member=self, to_member=other).delete()
        MemberConnection.objects.filter(from_member=other, to_member=self).delete()
        
    @property
    def icon_name(self):
        if self.role == Member.BOT:
            return "fas fa-robot"
        elif self.role == Member.STAFF:
            return "fas fa-user-tie"
        else:
            return "fas fa-user"

    def __str__(self):
        return self.name

    def merge_with(self, other_member):
        if self.user is None and other_member.user is not None :
            self.user = other_member.user
        if other_member.first_seen is not None and (self.first_seen is None or self.first_seen > other_member.first_seen):
            self.first_seen = other_member.first_seen
        if other_member.last_seen is not None and (self.last_seen is None or self.last_seen < other_member.last_seen):
            self.last_seen = other_member.last_seen
        if other_member.role == Member.BOT:
            self.role = Member.BOT
        elif other_member.role == Member.STAFF and self.role != Member.BOT:
            self.role = Member.STAFF
        if self.email_address is None and other_member.email_address is not None:
            self.email_address = other_member.email_address
        self_contacts = [c.detail for c in self.contact_set.all()]
        other_contacts = [c.detail for c in other_member.contact_set.all()]
        if other_member.name is not None and self.name in self_contacts and other_member.name not in other_contacts:
            self.name = other_member.name

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

        for level in MemberLevel.objects.filter(member=other_member):
            try:
                self_level = MemberLevel.objects.get(community=self.community, project=level.project, member=self)
                if level.level > self_level.level:
                    self_level.level = level.level
                    self_level.timestamp = level.timestamp
                    self_level.save()
            except MemberLevel.DoesNotExist:
                level.member = self
                level.save()
        self.save()
        other_member.delete()

class MemberWatch(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    start = models.DateTimeField(auto_now_add=True)
    end = models.DateTimeField(null=True, blank=True)
    level = models.SmallIntegerField(choices=DEFAULT_TAGS.items(), default=WARNING)

class GiftType(models.Model):
    class Meta:
        ordering = ('discontinued', 'name')
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    contents = models.TextField()
    discontinued = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.discontinued is not None:
            return "%s (discontinued)" % self.name
        else:
            return self.name

class Gift(models.Model):
    class Meta:
        ordering = ('-sent_date',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    gift_type = models.ForeignKey(GiftType, on_delete=models.SET_NULL, null=True, blank=False)
    reason = models.TextField(blank=True)
    sent_date = models.DateTimeField()
    received_date = models.DateTimeField(null=True, blank=True)
    tracking = models.CharField(max_length=512, null=True, blank=True)

    def __str__(self):
        if self.gift_type is not None:
            return "%s for %s" % (self.gift_type.name, self.member.name)
        else:
            return "Unknown gift for %s" % self.member.name

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
    enabled = models.BooleanField(default=True)

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

    @property
    def connector_name(self):
        return ConnectionManager.display_name(self.source.connector)

    def __str__(self):
        return self.name

class Contact(ImportedDataModel):
    class Meta:
        ordering = ("detail",)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    detail = models.CharField(max_length=256)
    name = models.CharField(max_length=256, null=True, blank=True)
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

class Project(models.Model):
    class Meta:
        ordering = ("name",)
    name = models.CharField(max_length=256)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    owner = models.ForeignKey(Member, related_name='owned_projects', on_delete=models.SET_NULL, null=True, blank=True)
    default_project = models.BooleanField(default=False)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)
    channels = models.ManyToManyField(Channel, blank=True)
    threshold_period = models.SmallIntegerField(verbose_name="Activity Period", default=365, help_text="Timerange in days to look at for level activity")
    threshold_user = models.SmallIntegerField(verbose_name="User level", default=1, help_text="Number of conversations needed to become a User")
    threshold_participant = models.SmallIntegerField(verbose_name="Participant level", default=3, help_text="Number of conversations needed to become a Participant")
    threshold_contributor = models.SmallIntegerField(verbose_name="Contributor level", default=1, help_text="Number of contributions needed to become a Contributor")
    threshold_core = models.SmallIntegerField(verbose_name="Core level", default=5, help_text="Number of contributions needed to become a Core Contributor")

    @property
    def collaborators(self):
        return MemberLevel.objects.filter(project=self, level__gte=MemberLevel.PARTICIPANT)

    def __str__(self):
        return "%s (%s)" % (self.name, self.community)

        
class MemberLevel(models.Model):
    USER = 0
    PARTICIPANT = 1
    CONTRIBUTOR = 2
    CORE = 3
    LEVEL_MAP = {
        USER: 'Visitor',
        PARTICIPANT: 'Participant',
        CONTRIBUTOR: 'Contributor',
        CORE: 'Core'
    }
    LEVEL_CHOICES = [
        (CORE, 'Core'),
        (CONTRIBUTOR, 'Contributor'),
        (PARTICIPANT, 'Participant'),
        (USER, 'Visitor'),
    ]
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, related_name='collaborations', on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    level = models.SmallIntegerField(choices=LEVEL_CHOICES, default=USER, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    @property
    def level_name(self):
        return MemberLevel.LEVEL_MAP[self.level]

class Task(TaggableModel):
    class Meta:
        ordering = ("done", "due",)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=False, blank=False)
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
    location = models.URLField(max_length=512, null=True, blank=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.title, self.community)

class Promotion(TaggableModel, ImportedDataModel):
    class Meta:
        verbose_name_plural = _("Promotions")
        ordering = ('-timestamp',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=256)
    timestamp = models.DateTimeField(db_index=True)
    location = models.URLField(max_length=512, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    promoters = models.ManyToManyField(Member)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return "%s (%s)" % (self.title, self.community)

class Event(ImportedDataModel):
    class Meta:
        verbose_name_plural = _("Events")
        ordering = ('start_timestamp',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=256)
    description = models.TextField(null=True, blank=True)
    start_timestamp = models.DateTimeField(db_index=True)
    end_timestamp = models.DateTimeField()
    location = models.URLField(max_length=512, null=True, blank=True)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)
    promotions = models.ManyToManyField(Promotion, blank=True)

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