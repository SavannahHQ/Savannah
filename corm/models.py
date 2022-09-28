import datetime, pytz
import uuid
from django.db import models
from django.db.models import F, Q, Count, Max, QuerySet
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404, reverse
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.contrib.messages.constants import DEFAULT_TAGS, WARNING
from django.utils.safestring import mark_safe
from jsonfield.fields import JSONField

from imagekit import ImageSpec
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

from corm.connectors import ConnectionManager

class IsNull(models.Func):
    _output_field = models.BooleanField()
    arity = 1
    template = '%(expressions)s IS NULL'

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
    auth_refresh = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        return "%s on %s" % (self.user, ConnectionManager.display_name(self.connector))

class ManagementPermissionMixin(object):

    def upgrade_message(self, request, msg):
        messages.info(request, "%s. <a class=\"btn btn-sm btn-success\" href=\"%s\">Upgrade your plan</a> to add more." % (msg, reverse('billing:upgrade', kwargs={"community_id":self.community.id})))
        
    @property
    def name(self):
        return "Unknown Plan"

    @property
    def managers(self):
        return 1

    def can_add_manager(self):
        if self.managers > 0:
            return self.community.managers.user_set.all().count() < self.managers
        else:
            return True

    @property
    def sources(self):
        return 3

    def can_add_source(self):
        if self.sources > 0:
            return self.community.source_set.filter(enabled=True).exclude(connector='corm.plugins.null').count() < self.sources
        else:
            return True

    @property
    def tags(self):
        return 3

    def can_add_tag(self):
        if self.tags > 0:
            return self.community.tag_set.all().count() < self.tags
        else:
            return True

    @property
    def projects(self):
        return 3

    def can_add_project(self):
        if self.projects > 0:
            return self.community.project_set.filter(default_project=False).count() < self.projects
        else:
            return True

    @property
    def import_days(self):
        return 1

    def max_import_date(self):
        if self.import_days > 0:
            return self.community.created - datetime.timedelta(days=self.import_days)
        else:
            return self.community.created - datetime.timedelta(years=5)

    @property
    def retention_days(self):
        return 1

    def max_retention_date(self):
        if self.retention_days > 0:
            return datetime.datetime.utcnow() - datetime.timedelta(days=self.retention_days)
        else:
            return self.community.created - datetime.timedelta(years=3)

    @property
    def sales_itegration(self):
        return False

    def can_add_sales_source(self):
        return self.sales_itegration

class NoManagement(ManagementPermissionMixin):
    def __init__(self, community, metadata={}):
        self.community = community
        self.metadata = metadata

    def update(self):
        pass

    @property 
    def is_billable(self):
        return False

class DemoManagement(ManagementPermissionMixin):
    def __init__(self, community):
        self.community = community
        self.metadata = {}

    def update(self):
        pass

    @property 
    def is_billable(self):
        return False

    @property
    def name(self):
        return "Demonstration Plan"

    @property
    def managers(self):
        return 0

    @property
    def sources(self):
        return 0

    @property
    def tags(self):
        return 0

    @property
    def projects(self):
        return 0

    @property
    def import_days(self):
        return 0

    @property
    def retention_days(self):
        return 0

    @property
    def sales_itegration(self):
        return True

class Community(models.Model):
    SETUP = 0
    ACTIVE = 1
    SUSPENDED = 2
    DEACTIVE = 3
    ARCHIVED = 4
    DEMO = 5

    STATUS_CHOICES = [
        (SETUP, 'Setup'),
        (ACTIVE, 'Active'),
        (SUSPENDED, 'Suspended'),
        (DEACTIVE, 'Deactive'),
        (ARCHIVED, 'Archived'),
        (DEMO, 'Demonstration'),
    ]
    STATUS_NAMES = {
        SETUP: "Setup",
        ACTIVE: "Active",
        SUSPENDED: "Suspended",
        DEACTIVE: "Deactive",
        ARCHIVED: "Archived",
        DEMO: "Demonstration",
    }
    class Meta:
        verbose_name = _("Community")
        verbose_name_plural = _("Communities")
        ordering = ("name",)
    name = models.CharField(verbose_name="Community Name", max_length=256)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    managers = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    logo = models.ImageField(verbose_name="Community Icon", help_text="Will be resized to a 32x32px icon.", upload_to='community_logos', null=True, blank=True)
    icon = ImageSpecField(source='logo', spec=Icon)
    created = models.DateTimeField(auto_now_add=True)
    status = models.SmallIntegerField(choices=STATUS_CHOICES, default=SETUP)

    suggest_tag = models.BooleanField(default=True, help_text="Suggest new Tags based on Conversation text")
    suggest_company = models.BooleanField(default=True, help_text="Suggest new Companies based on email addresses")
    suggest_merge = models.BooleanField(default=True, help_text="Suggest merging accounts belonging to the same person")
    suggest_contribution = models.BooleanField(default=True, help_text="Suggest Contributions based on Conversation text")
    suggest_task = models.BooleanField(default=True, help_text="Suggest Tasks to help engage with your Members")

    inactivity_threshold_previous_activity = models.PositiveSmallIntegerField(default=50, help_text="Amount of previous activity required before you will be notified that a member has become inactive.")
    inactivity_threshold_previous_days = models.PositiveSmallIntegerField(default=90, help_text="Number of days into the past to check for activity to meet the notification threshold")
    inactivity_threshold_days = models.PositiveSmallIntegerField(default=30, help_text="Number of days of inactivity before triggering a notification")

    resuming_threshold_previous_activity = models.PositiveSmallIntegerField(default=20, help_text="Amount of previous activity required before you will be notified that an inactive member had become active again")
    resuming_threshold_previous_days = models.PositiveSmallIntegerField(default=90, help_text="Number of days into the past to check for activity to meet the notification threshold")
    resuming_threshold_days = models.PositiveSmallIntegerField(default=30, help_text="Number of days of inactivity before triggering a notification on new activity")

    @property
    def manual_source(self):
        source, created = Source.objects.get_or_create(community=self, name="Manual Entry", connector='corm.plugins.null', icon_name='fas fa-edit')
        return source

    @property
    def management(self):
        try:
            return self._management
        except:
            if self.status == self.DEMO:
                return DemoManagement(community=self)
            else:
                return NoManagement(community=self, metadata={
                    'name': 'No Plan'
                })

    @property
    def email(self):
        if self.owner and self.owner.email:
            return self.owner.email
        else:
            return "support@savannahhq.com"

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

    @property    
    def contribution_type_names(self):
        ctype_query = self.contributiontype_set.all().order_by('name')
        # ctype_query = ctype_query.annotate(contrib_count=Count('contribution')).filter(contrib_count__gt=0)
        try:
            return [ctype.name for ctype in ctype_query.distinct('name')]
        except:
            ctypes = []
            for ctype in ctype_query:
                if ctype.name not in ctypes:
                    ctypes.append(ctype.name)
            return ctypes

    def __str__(self):
        return self.name

class Insight(models.Model):
    class InsightLevel(models.TextChoices):
        SUCCESS = "success"
        INFO = "info"
        WARNING = "warning"
        DANGER = "danger"
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=256, null=False, blank=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(choices=InsightLevel.choices, default=InsightLevel.INFO, max_length=20)
    text = models.TextField()
    link = models.CharField(max_length=256, blank=True, null=True)
    cta = models.CharField(max_length=256, blank=True, null=True, default='More...')
    unread = models.BooleanField(default=True, blank=False, db_index=True)
    uid = models.CharField(max_length=256, null=False, blank=False)

    def create(community, recipient, uid, title, text, level=InsightLevel.INFO, link=None, cta="More..."):
        if isinstance(recipient, Group):
            recipients = recipient.user_set.all()
        elif isinstance(recipient, (QuerySet, list)):
            recipients = recipient
        else:
            recipients = [recipient]

        for recipient in recipients:
            insight = Insight.objects.create(
                community=community,
                recipient=recipient,
                uid=uid,
                title=title,
                level=level,
                unread=True,
                link=link,
                cta=cta,
                text=text
            )
            
class Tag(models.Model):
    class Meta:
        ordering = ("name",)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    color = models.CharField(max_length=16)
    keywords = models.CharField(max_length=256, null=True, blank=True, help_text=_("Comma-separated list of words. If found in a conversation, this tag will be applied."))
    last_changed = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    connector = models.CharField(max_length=256, null=True, blank=True, choices=ConnectionManager.CONNECTOR_CHOICES)
    editable = models.BooleanField(default=True)

    @property
    def connector_name(self):
        if self.connector:
            return ConnectionManager.display_name(self.connector)
        else:
            return ""

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
    community = models.ForeignKey(Community, on_delete=models.CASCADE, null=False, blank=False)
    first_connected = models.DateTimeField(db_index=True)
    last_connected = models.DateTimeField(db_index=True)
    connection_count = models.PositiveIntegerField(default=1)
    
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
    avatar_url = models.URLField(max_length=512, null=True, blank=True)
    role = models.CharField(max_length=32, choices=MEMBER_ROLE, default=COMMUNITY)
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True)

    connections = models.ManyToManyField('Member', through='MemberConnection')

    # Settings
    auto_update_name = models.BooleanField(default=True, verbose_name='Auto Update Name')
    auto_update_role = models.BooleanField(default=True, verbose_name='Auto Update Role')
    auto_update_company = models.BooleanField(default=True, verbose_name='Auto Update Company')
    auto_update_email = models.BooleanField(default=True, verbose_name='Auto Update Email Address')
    auto_update_avatar = models.BooleanField(default=True, verbose_name='Auto Update Avatar')

    def set_company(self, company):
        if company is None:
            if self.company.is_staff and self.role == Member.STAFF:
                self.role = Member.COMMUNITY
            self.tags.remove(company.tag)
            self.company = None
        else:
            if company.is_staff and self.role == Member.COMMUNITY:
                self.role = Member.STAFF
            self.tags.add(company.tag)
            self.company = company
        self.save()

    @property
    def default_level(self):
        if hasattr(self, '_default_project'):
            return self._default_project
        try:
            self._default_project = self.collaborations.get(project__default_project=True)
            return self._default_project
        except Exception as e:
            return None

    @property
    def suggest_company(self):
        if self.company or not self.email_address:
            return False
        try:
            user, domain = self.email_address.split('@', maxsplit=1)
            if domain not in settings.PUBLIC_EMAIL_DOMAINS:
                return True
        except:
            return False
            
    def is_connected(self, other):
        return MemberConnection.objects.filter(from_member=self, to_member=other).count() > 0

    def add_connection(self, other, timestamp=None, count=1):
        if self.id == other.id:
            return
        if self.is_connected(other):
            if count > 1:
                MemberConnection.objects.filter(from_member=self, to_member=other, last_connected__lt=timestamp).update(last_connected=timestamp, connection_count=count)
                MemberConnection.objects.filter(from_member=other, to_member=self, last_connected__lt=timestamp).update(last_connected=timestamp, connection_count=count)
            else:
                MemberConnection.objects.filter(from_member=self, to_member=other, last_connected__lt=timestamp).update(last_connected=timestamp)
                MemberConnection.objects.filter(from_member=other, to_member=self, last_connected__lt=timestamp).update(last_connected=timestamp)
        else:              
            MemberConnection.objects.create(from_member=self, to_member=other, community=self.community, first_connected=timestamp, last_connected=timestamp, connection_count=count)
            MemberConnection.objects.create(from_member=other, to_member=self, community=self.community, first_connected=timestamp, last_connected=timestamp, connection_count=count)
        
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
        merge_record = MemberMergeRecord.from_member(other_member, self)

        if self.user is None and other_member.user is not None :
            self.user = other_member.user
            other_member.user = None
            other_member.save()
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
        if self.mailing_address is None and other_member.mailing_address is not None:
            self.mailing_address = other_member.mailing_address
        if self.phone_number is None and other_member.phone_number is not None:
            self.phone_number = other_member.phone_number
        if self.company is None and other_member.company is not None:
            self.company = other_member.company

        self_contacts = [c.detail for c in self.contact_set.all()]
        other_contacts = [c.detail for c in other_member.contact_set.all()]
        if other_member.name is not None and self.name in self_contacts and other_member.name not in other_contacts:
            self.name = other_member.name

        Contact.objects.filter(member=other_member).update(member=self)
        Note.objects.filter(member=other_member).update(member=self)
        MemberConnection.objects.filter(from_member=other_member).update(from_member=self)
        MemberConnection.objects.filter(to_member=other_member).update(to_member=self)
        Activity.objects.filter(member=other_member).update(member=self)
        Conversation.objects.filter(speaker=other_member).update(speaker=self)
        Contribution.objects.filter(author=other_member).update(author=self)
        Gift.objects.filter(member=other_member).update(member=self)
        MemberWatch.objects.filter(member=other_member).update(member=self)
        Opportunity.objects.filter(member=other_member).update(member=self)

        for tag in other_member.tags.all():
            self.tags.add(tag)

        Participant.objects.filter(initiator=other_member).update(initiator=self)
        Participant.objects.filter(member=other_member).update(member=self)

        for task in Task.objects.filter(project__community=self.community, stakeholders=other_member):
            task.stakeholders.add(self)
            task.stakeholders.remove(other_member)

        for level in MemberLevel.objects.filter(member=other_member):
            try:
                self_level = MemberLevel.objects.get(community=self.community, project=level.project, member=self)
                if level.level > self_level.level:
                    self_level.level = level.level
                if level.timestamp > self_level.timestamp:
                    self_level.timestamp = level.timestamp
                self_level.conversation_count += level.conversation_count
                self_level.contribution_count += level.contribution_count
                self_level.save()
            except MemberLevel.DoesNotExist:
                level.member = self
                level.save()

        for attendance in EventAttendee.objects.filter(member=other_member):
            try:
                self_attendance = EventAttendee.objects.get(community=self.community, event=attendance.event)
                if attendance.role > self_attendance.role:
                    self_attendance.role = attendance.role
                self_attendance.save()
            except:
                attendance.member = self
                attendance.save()

        self.save()
        other_member.delete()

class MemberMergeRecord(models.Model):
    community =  models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256, db_index=True)
    merged_with = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL)
    merged_date = models.DateField(auto_now_add=True)
    data = data = JSONField(null=True, blank=True)

    @classmethod
    def _serialize(self, member):
        if member.last_seen is not None:
            last_seen = member.last_seen.strftime('%Y-%m-%dT%H:%M:%S.%f')
        else:
            last_seen = None
        data = {
            'name': member.name,
            'email_address': member.email_address,
            'first_seen': member.first_seen.strftime('%Y-%m-%dT%H:%M:%S.%f'),
            'last_seen': last_seen,
            'mailing_address': member.mailing_address,
            'phone_number': member.phone_number,
            'avatar_url': member.avatar_url,
            'role': member.role,
            'company': member.company_id,
            'identities': [ident.id for ident in Contact.objects.filter(member=member)],
            'tags': [tag.id for tag in member.tags.all()],
            'notes': [note.id for note in Note.objects.filter(member=member)],
            'gifts': [gift.id for gift in Gift.objects.filter(member=member)],
            'activity': [c.id for c in Activity.objects.filter(member=member)],
            'conversations': [c.id for c in Conversation.objects.filter(speaker=member)],
            'contributions': [c.id for c in Contribution.objects.filter(author=member)],
            'event_attendance': [c.id for c in EventAttendee.objects.filter(member=member)],
            'watches': [w.id for w in MemberWatch.objects.filter(member=member)],
            'tasks': [t.id for t in Task.objects.filter(stakeholders=member)],
            'opportunities': [o.id for o in Opportunity.objects.filter(member=member)],
            'levels': dict([(level.project_id, (level.level, level.timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f'))) for level in MemberLevel.objects.filter(member=member)])
        }
        return data

    @classmethod
    def from_member(cls, member, target=None):
        data = {}
        data['removed'] = cls._serialize(member)
        if target:
            data['original'] = cls._serialize(target)
        record = MemberMergeRecord.objects.create(community=member.community, name=member.name, merged_with=target, data=data)
        return record


    def restore(self):
        now = datetime.datetime.utcnow()

        # Restore the removed member
        removed = self.data['removed']
        member = Member.objects.create(
            community=self.community, 
            name=self.name,
            first_seen=removed.get('first_seen', now),
            last_seen=removed.get('last_seen', removed.get('first_seen', now)),
            email_address=removed.get('email_address'),
            phone_number=removed.get('phone_number'),
            mailing_address=removed.get('mailing_address'),
            avatar_url=removed.get('avatar_url'),
            role=removed.get('role', Member.COMMUNITY),
        )
        try:
            member.company = Company.objects.get(id=removed.get('company'))
        except:
            pass
        member.save()

        Contact.objects.filter(id__in=removed.get('identities', [])).update(member=member)
        Note.objects.filter(id__in=removed.get('notes', [])).update(member=member)
        Gift.objects.filter(id__in=removed.get('gifts', [])).update(member=member)
        Activity.objects.filter(id__in=removed.get('activity', [])).update(member=member)
        Conversation.objects.filter(id__in=removed.get('conversations', [])).update(speaker=member)
        Contribution.objects.filter(id__in=removed.get('contributions', [])).update(author=member)
        EventAttendee.objects.filter(id__in=removed.get('event_attendance', [])).update(member=member)

        member.tags.set(Tag.objects.filter(id__in=removed.get('tags', [])).all())

        for task in Task.objects.filter(id__in=removed.get('tasks', [])):
            task.stakeholders.remove(self.merged_with)
            task.stakeholders.add(member)

        for project_id in removed.get('levels', []):
            try:
                project = Project.objects.get(id=project_id)
                level, tstamp = removed['levels'][project_id]
                MemberLevel.objects.create(community=member.community, timestamp=tstamp, member=member, level=level, project=project)
            except:
                pass

        # Reset the original member
        original = self.data.get('original')
        if original:
            original_first_seen = datetime.datetime.strptime(original.get('first_seen'), '%Y-%m-%dT%H:%M:%S.%f')
            original_last_seen = datetime.datetime.strptime(original.get('last_seen'), '%Y-%m-%dT%H:%M:%S.%f')
            removed_first_seen = datetime.datetime.strptime(removed.get('first_seen'), '%Y-%m-%dT%H:%M:%S.%f')
            if removed.get('last_seen'):
                removed_last_seen = datetime.datetime.strptime(removed.get('last_seen'), '%Y-%m-%dT%H:%M:%S.%f')
            else:
                removed_last_seen = None

            if original.get('name') != self.merged_with.name and removed.get('name') == self.merged_with.name:
                self.merged_with.name = original.get('name')
            if original_first_seen != self.merged_with.first_seen and removed_first_seen == self.merged_with.first_seen:
                self.merged_with.first_seen = original_first_seen
            if original_last_seen != self.merged_with.last_seen and removed_last_seen == self.merged_with.last_seen:
                self.merged_with.last_seen = original_last_seen
            if original.get('email_address') != self.merged_with.email_address and removed.get('email_address') == self.merged_with.email_address:
                self.merged_with.email_address = original.get('email_address')
            if original.get('phone_number') != self.merged_with.phone_number and removed.get('phone_number') == self.merged_with.phone_number:
                self.merged_with.phone_number = original.get('phone_number')
            if original.get('mailing_address') != self.merged_with.mailing_address and removed.get('mailing_address') == self.merged_with.mailing_address:
                self.merged_with.mailing_address = original.get('mailing_address')
            if original.get('role') != self.merged_with.role and removed.get('role') == self.merged_with.role:
                self.merged_with.role = original.get('role')
            if original.get('company') != self.merged_with.company_id and removed.get('company') == self.merged_with.company_id:
                self.merged_with.company_id = original.get('company')

            added_tags = set(removed.get('tags', [])) - set(original.get('tags', []))
            for tag_id in added_tags:
                try:
                    tag = Tag.objects.get(id=tag_id)
                    self.merged_with.tags.remove(tag)
                except:
                    pass
            self.merged_with.save()
        self.delete()
        return member

class MemberWatch(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    start = models.DateTimeField(auto_now_add=True)
    end = models.DateTimeField(null=True, blank=True)
    level = models.SmallIntegerField(choices=DEFAULT_TAGS.items(), default=WARNING)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_channel = models.ForeignKey('Channel', on_delete=models.SET_NULL, null=True, blank=True)

class ImpactReport(models.Model):
    class Meta:
        ordering = ('start_timestamp',)
    name = models.CharField(max_length=256)
    start_timestamp = models.DateTimeField(null=False, blank=False)
    impact_score = models.IntegerField(default=0, null=False, blank=False)
    impact_1d = models.IntegerField(default=0, null=False, blank=False)
    impact_7d = models.IntegerField(default=0, null=False, blank=False)
    impact_15d = models.IntegerField(default=0, null=False, blank=False)
    impact_30d = models.IntegerField(default=0, null=False, blank=False)
    impact_60d = models.IntegerField(default=0, null=False, blank=False)
    impact_90d = models.IntegerField(default=0, null=False, blank=False)

    def __str__(self):
        return self.name

class GiftType(models.Model):
    class Meta:
        ordering = ('discontinued', 'name')
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    contents = models.TextField()
    discontinued = models.DateTimeField(null=True, blank=True)
    impact = models.IntegerField(default=0, null=False, blank=False)

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
    impact = models.IntegerField(default=0, null=False, blank=False)

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
    api_key = models.CharField(max_length=256, null=True, blank=True)
    icon_name = models.CharField(max_length=256, null=True, blank=True)
    first_import = models.DateTimeField(null=True, blank=True)
    last_import = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    import_failed_attempts = models.SmallIntegerField(default=0)
    import_failed_message = models.CharField(max_length=256, null=True, blank=True)

    @property
    def import_failed(self):
        return self.import_failed_attempts > 0
        
    @property
    def activity_set(self):
        return Contribution.objects.filter(contribution_type__source=self)

    @property
    def conversation_set(self):
        return Conversation.objects.filter(channel__source=self)

    @property
    def has_engagement(self):
        return (self.activity_set.count() + self.conversation_set.count()) > 0

    @property
    def connector_name(self):
        return ConnectionManager.display_name(self.connector)

    @property
    def plugin(self):
        return ConnectionManager.CONNECTOR_PLUGINS.get(self.connector)
        
    def __str__(self):
        return self.name

class Channel(ImportedDataModel):
    class Meta:
        ordering = ("name",)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)
    oldest_import = models.DateTimeField(null=True, blank=True)
    first_import = models.DateTimeField(null=True, blank=True)
    last_import = models.DateTimeField(null=True, blank=True)
    import_failed_attempts = models.SmallIntegerField(default=0)
    import_failed_message = models.CharField(max_length=256, null=True, blank=True)
    enabled = models.BooleanField(default=True)

    @property
    def import_failed(self):
        return self.import_failed_attempts > 0

    @property
    def connector_name(self):
        return ConnectionManager.display_name(self.source.connector)

    def get_origin_url(self):
        try:
            return ConnectionManager.CONNECTOR_PLUGINS[self.source.connector].get_channel_url(self)
        except Exception as e:
            print(e)
            return None


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
    avatar_url = models.URLField(max_length=512, null=True, blank=True)

    @property
    def link_url(self):
        if hasattr(self, '_identity_url'):
            return self._identity_url
        else:
            self._identity_url = ConnectionManager.get_identity_url(self)
            return self._identity_url

    def __str__(self):
        return "%s (%s)" % (self.detail, self.source.name)

class Participant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey('Conversation', related_name='participation', on_delete=models.CASCADE)
    member = models.ForeignKey(Member, related_name='participant_in', on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, null=True)
    initiator = models.ForeignKey(Member, related_name='initiator_of', on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(db_index=True)

class Activity(TaggableModel):
    class Meta:
        ordering = ("-timestamp",)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, related_name='activity', on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    icon_name = models.CharField(max_length=256, null=True, blank=True)
    short_description = models.CharField(max_length=256)
    long_description = models.CharField(max_length=256)
    location = models.URLField(max_length=512, null=True, blank=True)

    conversation = models.OneToOneField("Conversation", null=True, blank=True, on_delete=models.CASCADE)
    contribution = models.OneToOneField("Contribution", null=True, blank=True, on_delete=models.CASCADE)
    event_attendance = models.OneToOneField("EventAttendee", null=True, blank=True, on_delete=models.CASCADE)

    @property
    def participants(self):
        if self.conversation:
            return Member.objects.filter(participant_in__conversation=self.conversation)
        else:
            return Member.objects.none()
        
    def __str__(self):
        return self.short_description

class Hyperlink(models.Model):
    """
    For tracking links people mention in conversations
    """

    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    url = models.URLField()
    host = models.CharField(max_length=256)
    path = models.CharField(max_length=512)
    content_type = models.CharField(max_length=64, null=True, blank=True)
    ignored = models.BooleanField(default=False, help_text='Ignore links that are not interesting to you, or are added automatically to conversations.')

    def __str__(self):
        return self.url

class Conversation(TaggableModel, ImportedDataModel):
    class Meta:
        ordering = ("-timestamp",)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    speaker = models.ForeignKey(Member, related_name='speaker_in', on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    location = models.URLField(max_length=512, null=True, blank=True)
    thread_start = models.ForeignKey('Conversation', related_name='replies', on_delete=models.CASCADE, null=True, blank=True)
    contribution = models.OneToOneField('Contribution', related_name='conversation', on_delete=models.SET_NULL, null=True, blank=True)
    links = models.ManyToManyField(Hyperlink)

    @property
    def participants(self):
        return Member.objects.filter(participant_in__conversation=self)
        
    @classmethod
    def truncate(cls, content):
        if content is None:
            return ""
        truncated = False
        content = content.strip()
        if content.count('\n') >= 2:
            if content.count('\n') >= 3:
                truncated = True
            content = "\n".join(content.split('\n')[:3])

        if len(content) > 250:
            truncated = True
            content = content[:250]
        if truncated:
            content = content+"..."
        return content
  
    @property
    def brief(self):
        if self.content is not None:
            return Conversation.truncate(self.content)
        return ""

    def update_activity(self, from_activity=None):
        if from_activity:
            try :
                from_activity.conversation = self
                if self.speaker:
                    from_activity.member = self.speaker
                if self.content:
                    from_activity.long_description = Conversation.truncate(self.content)
                if self.location:
                    from_activity.location = self.location
                from_activity.save()
            except:
                # Conversation already has an activity
                pass        
        activity, created = Activity.objects.get_or_create(
            conversation=self,
            defaults = {
                'community':self.community,
                'source':self.source,
                'channel':self.channel,
                'member':self.speaker,
                'timestamp':self.timestamp,
                'icon_name':'fas fa-comments',
                'short_description':'Commented',
                'long_description':self.brief,
                'location':self.location
            }
        )
        if self.speaker:
            activity.member = self.speaker
        if self.content:
            activity.long_description = Conversation.truncate(self.content)
        if self.location:
            activity.location = self.location
        activity.save()
        if self.tags:
            activity.tags.add(*self.tags.all())
        return activity
        
    def __str__(self):
        if self.content is not None:
            content = self.content.strip()
            if len(content) > 2:
                try:
                    return content[:min(content.strip().replace('\n', ' '), 64)]
                except:
                    return content[:min(len(content), 64)]
        return str(self.timestamp)

class Project(models.Model):
    class Meta:
        ordering = ("name",)
    name = models.CharField(max_length=256)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    owner = models.ForeignKey(Member, related_name='owned_projects', on_delete=models.SET_NULL, null=True, blank=True)
    default_project = models.BooleanField(default=False)
    tag = models.ForeignKey(Tag, verbose_name="Content tag", related_name='projects_by_content', on_delete=models.SET_NULL, null=True, blank=True, help_text='Any content with this tag will be included in this project\'s activity')
    member_tag = models.ForeignKey(Tag, verbose_name="Member tag", related_name='projects_by_member', on_delete=models.SET_NULL, null=True, blank=True, help_text='Any activity by a member with this tag will be included in this project\'s activity')
    channels = models.ManyToManyField(Channel, blank=True, help_text='Any activity in these channels will be included in this project\'s activity')
    threshold_period = models.SmallIntegerField(verbose_name="Activity Period", default=365, help_text="Timerange in days to look at for level activity")
    threshold_user = models.SmallIntegerField(verbose_name="Visitor level", default=1, help_text="Number of conversations needed to become a Visitor")
    threshold_participant = models.SmallIntegerField(verbose_name="Participant level", default=3, help_text="Number of conversations needed to become a Participant")
    threshold_contributor = models.SmallIntegerField(verbose_name="Contributor level", default=1, help_text="Number of contributions needed to become a Contributor")
    threshold_core = models.SmallIntegerField(verbose_name="Core level", default=5, help_text="Number of contributions needed to become a Core Contributor")

    @property
    def color(self):
        if self.member_tag is not None:
            return self.member_tag.color
        elif self.tag is not None:
            return self.tag.color
        else:
            return '8a8a8a'
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
    conversation_count = models.IntegerField(default=0)
    contribution_count = models.IntegerField(default=0)

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
    detail = models.TextField(null=True, blank=True)
    due = models.DateTimeField()
    done = models.DateTimeField(null=True, blank=True, db_index=True)
    stakeholders = models.ManyToManyField(Member)
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def past_due(self):
        return self.due < datetime.datetime.utcnow()

    @property
    def is_done(self):
        return self.done is not None

    def __str__(self):
        return self.name

    @property
    def owner_name(self):
        try:
            manager = ManagerProfile.objects.get(community=self.community, user=self.owner)
            return str(manager)
        except ManagerProfile.DoesNotExist:
            if self.owner.first_name:
                return self.owner.get_full_name()
            return self.owner.username

class ContributionType(models.Model):
    class Meta:
        verbose_name = _("Contribution Type")
        verbose_name_plural = _("Contribution Types")
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=256)
    feed = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.name

class Contribution(TaggableModel, ImportedDataModel):
    class Meta:
        verbose_name_plural = _("Contributions")
        ordering = ('-timestamp',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    contribution_type = models.ForeignKey(ContributionType, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=256)
    timestamp = models.DateTimeField(db_index=True)
    author = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True)
    location = models.URLField(max_length=512, null=True, blank=True)

    def update_activity(self, from_activity=None):
        if from_activity:
            try :
                from_activity.contribution = self
                from_activity.save()
            except:
                # Contribution already has an activity
                pass
        activity, created = Activity.objects.update_or_create(
            contribution=self,
            defaults = {
                'community':self.community,
                'source':self.source,
                'channel':self.channel,
                'member':self.author,
                'timestamp':self.timestamp,
                'icon_name':'fas fa-shield-alt',
                'short_description':self.contribution_type.name,
                'long_description':self.title,
                'location':self.location
            }
        )
        if self.tags:
            activity.tags.add(*self.tags.all())
        return activity
        
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
    impact = models.IntegerField(default=0, null=False, blank=False)

    def __str__(self):
        return "%s (%s)" % (self.title, self.community)

class Event(ImportedDataModel):
    class Meta:
        verbose_name_plural = _("Events")
        ordering = ('start_timestamp',)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    title = models.CharField(max_length=256)
    description = models.TextField(null=True, blank=True)
    start_timestamp = models.DateTimeField(db_index=True)
    end_timestamp = models.DateTimeField()
    location = models.URLField(max_length=512, null=True, blank=True, verbose_name='Event URL')
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True)
    promotions = models.ManyToManyField(Promotion, blank=True)
    impact = models.IntegerField(default=0, null=False, blank=False)

    @property
    def attendees(self):
        return Member.objects.filter(event_attendance__event=self)

    @property
    def hosts(self):
        return Member.objects.filter(event_attendance__event=self, event_attendance__role=EventAttendee.HOST)

    @property
    def speakers(self):
        return Member.objects.filter(event_attendance__event=self, event_attendance__role=EventAttendee.SPEAKER)

    @property
    def staff(self):
        return Member.objects.filter(event_attendance__event=self, event_attendance__role=EventAttendee.STAFF)

    def __str__(self):
        return "%s (%s)" % (self.title, self.community)

class EventAttendee(models.Model):
    GUEST = "guest"
    HOST = "host"
    SPEAKER = "speaker"
    STAFF = "staff"
    ATTENDEE_ROLE = [
        (GUEST, 'Guest'),
        (HOST, 'Host'),
        (SPEAKER, 'Speaker'),
        (STAFF, "Staff"),
    ]
    ROLE_NAME = {
        GUEST: "Guest",
        HOST: "Host",
        SPEAKER: "Speaker",
        STAFF: "Staff",
    }    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, related_name="rsvp", on_delete=models.CASCADE)
    member = models.ForeignKey(Member, related_name='event_attendance', on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    role = models.CharField(max_length=32, choices=ATTENDEE_ROLE, default=GUEST)
 
    def update_activity(self, from_activity=None):
        if from_activity:
            try :
                from_activity.event_attendance = self
                from_activity.save()
            except:
                # Contribution already has an activity
                pass        
        activity, created = Activity.objects.get_or_create(
            event_attendance=self,
            defaults = {
                'community':self.community,
                'source':self.event.source,
                'channel':self.event.channel,
                'member':self.member,
                'timestamp':self.timestamp,
                'icon_name':'fas fa-calendar-alt',
                'short_description':'Attended Event',
                'long_description':self.event.title,
                'location':self.event.location
            }
        )
        if self.event.tag:
            activity.tags.add(self.event.tag)
        return activity

    def __str__(self):
        return "%s at %s" % (self.member, self.event)

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
                return self.content[:min(len(self.content), 64)]
        else:
            return str(self.timestamp)

    @property
    def author_name(self):
        try:
            manager = ManagerProfile.objects.get(community=self.member.community, user=self.author)
            return str(manager)
        except ManagerProfile.DoesNotExist:
            if self.author.first_name:
                return self.author.get_full_name()
            return self.author.username

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

    def accept_action(self, user):
        raise NotImplementedError

    def act_on_suggestion(self, user, action):
        self.actioned_at = datetime.datetime.utcnow()
        self.actioned_by = user
        self.status = action
        self.save()

    def accept(self, user):
        update_suggestion = self.accept_action(user)
        if update_suggestion is not False:
            self.act_on_suggestion(user, Suggestion.ACCEPTED)

    def reject(self, user):
        self.act_on_suggestion(user, Suggestion.REJECTED)

    def ignore(self, user):
        self.act_on_suggestion(user, Suggestion.IGNORED)

class SuggestMemberMerge(Suggestion):
    source_member = models.ForeignKey(Member, related_name='merge_to_suggestions', on_delete=models.CASCADE)    
    destination_member = models.ForeignKey(Member, related_name='merge_with_suggestions', on_delete=models.CASCADE)

    def accept_action(self, user):
        self.destination_member.merge_with(self.source_member)
        return False

class SuggestTag(Suggestion):
    keyword = models.CharField(max_length=50)
    score = models.SmallIntegerField(default=0)

    def accept(self, user, color):
        Tag.objects.create(community=self.community, name=self.keyword, keywords=self.keyword, color=color)
        self.delete()


class SuggestTask(Suggestion):
    stakeholder = models.ForeignKey(Member, related_name='task_suggestions', on_delete=models.CASCADE)    
    project = models.ForeignKey(Project, related_name='task_suggestions', on_delete=models.CASCADE)
    due_in_days = models.SmallIntegerField(default=0)
    name = models.CharField(max_length=256)
    description = models.TextField()

    def accept_action(self, user):
        new_task = Task.objects.create(
            community=self.community, 
            project=self.project,
            owner=user,
            name=self.name,
            detail=self.description,
            due=datetime.datetime.utcnow() + datetime.timedelta(days=self.due_in_days),
        )
        new_task.stakeholders.add(self.stakeholder)

class SuggestMemberTag(Suggestion):
    target_member = models.ForeignKey(MemberConnection, related_name='tag_suggestions', on_delete=models.CASCADE)    
    suggested_tag = models.ForeignKey(Tag, related_name='member_suggestions', on_delete=models.CASCADE)

    def accept_action(self, user):
        self.target_member.tags.add(self.suggested_tag)

class SuggestConversationTag(Suggestion):
    target_conversation = models.ForeignKey(Conversation, related_name='tag_suggestions', on_delete=models.CASCADE)    
    suggested_tag = models.ForeignKey(Tag, related_name='conversation_suggestions', on_delete=models.CASCADE)

    def accept_action(self, user):
        self.target_conversation.tags.add(self.suggested_tag)
        self.target_conversation.activity.tags.add(self.suggested_tag)

class SuggestConversationAsContribution(Suggestion):
    class Meta:
        ordering = ('-conversation__timestamp',)
    conversation = models.ForeignKey(Conversation, related_name='contribution_suggestions', on_delete=models.CASCADE)    
    activity = models.ForeignKey(Activity, related_name='contribution_suggestions', on_delete=models.CASCADE, null=True)    
    contribution_type = models.ForeignKey(ContributionType, related_name='contribution_suggestions', on_delete=models.CASCADE)
    source = models.ForeignKey(Source, related_name='contribution_suggestions', on_delete=models.CASCADE)
    title = models.CharField(max_length=256, null=False, blank=False)
    score = models.SmallIntegerField(default=0)


    def accept_action(self, user):
        # Anybody in the conversation other than the speaker made this contribution
        supporters = self.conversation.participation.exclude(member_id=self.conversation.speaker.id)
        for supporter in supporters:
            contrib, created = Contribution.objects.get_or_create(
                community=self.conversation.community,
                contribution_type=self.contribution_type,
                source=self.conversation.source,
                channel=self.conversation.channel,
                title=self.title,
                timestamp=self.conversation.timestamp,
                author=supporter.member,
                location=self.conversation.location,
            )
            if self.conversation.channel.tag is not None:
                contrib.tags.add(self.conversation.channel.tag)
            self.activity.contribution = contrib
            self.activity.icon_name = 'fas fa-shield-alt'
            self.activity.short_description = contrib.contribution_type.name
            self.activity.save()
        self.delete()
        return False

class Report(models.Model):
    GROWTH = 0
    ANNUAL = 1
    TYPES = {
        GROWTH: 'Growth',
        ANNUAL: 'Annual',
    }
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    title = models.CharField(max_length=256)
    report_type = models.SmallIntegerField(choices=TYPES.items())
    generated = models.DateTimeField(default=datetime.datetime.utcnow)
    data = models.TextField(null=True, blank=False)

    def __str__(self):
        return self.title

class TimezoneChoices:
    def __iter__(self):
        for tz in pytz.all_timezones:
            yield (tz, tz)

class ManagerProfile(models.Model):
    " Store profile information about a manager of a community"
    class Meta:
        ordering = ('last_seen__isnull', '-last_seen')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, verbose_name=_("Member Profile"), on_delete=models.SET_NULL, blank=True, null=True)
    realname = models.CharField(verbose_name=_("Preferred Name"), max_length=150, blank=True)
    contact_email = models.EmailField(verbose_name=_("Preferred Email"), null=True, blank=True)
    tz = models.CharField(
        max_length=32,
        verbose_name=_("Timezone"),
        default="UTC",
        choices=TimezoneChoices(),
        blank=False,
        null=False,
    )
    last_seen = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to='manager_avatars', null=True, blank=True)
    icon = ImageSpecField(source='avatar', spec=Icon)
    send_notifications = models.BooleanField(
        verbose_name=_("Send emails"), default=True
    )
    secret_key = models.UUIDField(default=uuid.uuid4, editable=True)

    class Meta:
        ordering = ("-last_seen",)

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        try:
            if self.realname:
                return self.realname
            elif self.user.first_name:
                return self.user.get_full_name()
            else:
                return self.user.username
        except:
            return _("Unknown Profile")

    @property
    def icon_path(self):
        try:
            return self.icon.url
        except:
            return "%ssavannah/manager_default.png" % settings.STATIC_URL

    @property
    def email(self):
        if self.contact_email:
            return self.contact_email
        else:
            return self.user.email

    @property
    def timezone(self):
        try:
            return pytz.timezone(self.tz)
        except:
            return pytz.utc

    def tolocaltime(self, dt):
        as_utc = pytz.utc.localize(dt)
        return as_utc.astimezone(self.timezone)

    def fromlocaltime(self, dt):
        local = self.timezone.localize(dt)
        return local.astimezone(pytz.utc)

class Company(models.Model):
    class Meta:
        ordering = ('name',)
        verbose_name_plural = "Companies"
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    website = models.URLField(max_length=512, null=True, blank=True)
    icon_url = models.URLField(max_length=512, null=True, blank=True)
    is_staff = models.BooleanField(default=False, help_text="Treat members as staff")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, null=True, blank=True)

    def merge_with(self, other):
        for domain in other.domains.all():
            domain.company = self
            domain.save()
        for group in other.groups.all():
            group.company = self
            group.save()
        for member in other.member_set.all():
            member.company = self
            member.save()
        other.delete()

    def set_tag(self, tag):
        if tag != self.tag:
            for member in Member.objects.filter(company=self):
                member.tags.remove(self.tag)
                member.tags.add(tag)
            self.tag = tag
            self.save()

    def set_tag_by_name(self, tag_id):
        if tag_id == '':
            self.set_tag(None)
        elif self.tag is None or tag_id != self.tag.id:
            new_tag = Tag.objects.get(community=self.community, id=tag_id)
            self.set_tag(new_tag)

    @property
    def logo_url(self):
        if self.icon_url:
            return self.icon_url
        elif self.website:
            domain = self.website.split("/")[2]
            if domain.startswith('www.'):
                domain = domain[4:]
            self.icon_url = "https://logo.clearbit.com/%s?size=32" % domain
            self.save()
            return self.icon_url
        else:
            return None

    @property
    def first_seen(self):
        try:
            first_convo = Conversation.objects.filter(speaker__community=self.community, speaker__company=self).order_by('timestamp')[0]
            return first_convo.timestamp
        except Exception as e:
            return None
        
    @property
    def last_seen(self):
        try:
            last_convo = Conversation.objects.filter(speaker__community=self.community, speaker__company=self).order_by('-timestamp')[0]
            return last_convo.timestamp
        except Exception as e:
            return None
        
    def __str__(self):
        return self.name

class CompanyDomains(models.Model):
    class Meta:
        ordering = ('domain',)
        verbose_name = "Company Domain"
        verbose_name_plural = "Company Domains"
    company = models.ForeignKey(Company, related_name='domains', on_delete=models.CASCADE)
    domain = models.CharField(max_length=256, null=True, blank=True, help_text=_('Email domain names'))

    def __str__(self):
        return self.domain
        
class SourceGroup(ImportedDataModel):
    company = models.ForeignKey(Company, related_name='groups', on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)

    def get_external_url(self):
        try:
            return self.source.plugin.get_company_url(self)
        except:
            return None

    def __str__(self):
        return self.name
        
class SuggestCompanyCreation(Suggestion):
    domain = models.CharField(max_length=256)

    def accept_action(self, user):
        default_domain = self.domain
        default_website = 'https://'+self.domain
        default_name = self.domain.rsplit('.', maxsplit=1)[0].replace('-', ' ').title()
        new_company = Company.objects.create(name=default_name, community=self.community, website=default_website)
        new_domain = CompanyDomains.objects.create(company=new_company, domain=default_domain)
        members = Member.objects.filter(community=self.community, company__isnull=True, email_address__endswith=default_domain, auto_update_company=True)
        for member in members:
            (identity, domain) = member.email_address.split('@', maxsplit=1)
            if domain == self.domain:
                member.company = new_company
                member.save()
        self.delete()
        return False

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

class EmailRecord(models.Model):
    """
    Model to store all the outgoing emails.
    """

    when = models.DateTimeField(null=False, auto_now_add=True)
    sender = models.ForeignKey(
        User,
        related_name="sent_messages",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    member = models.ForeignKey(
        Member,
        related_name="recv_messages",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    email = models.EmailField(null=False, blank=False)
    category = models.CharField(null=False, max_length=128)
    subject = models.CharField(null=False, max_length=128)
    body = models.TextField(null=False, max_length=1024)
    ok = models.BooleanField(null=False, default=True)

class UploadedFile(models.Model):
    UPLOADED = 0
    PENDING = 1
    PROCESSING = 2
    COMPLETE = 3
    FAILED = 4
    CANCELED = 5
    STATUS_CHOICES = [
        (UPLOADED, 'Uploaded'),
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (COMPLETE, 'Complete'),
        (FAILED, 'Failed'),
        (CANCELED, 'Canceled'),
    ]
    STATUS_NAMES = {
        UPLOADED: "Uploaded",
        PENDING: "Pending",
        PROCESSING: "Processing",
        COMPLETE: "Complete",
        FAILED: "Failed",
        CANCELED: "Canceled",
    }
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=512)
    mime_type = models.CharField(max_length=64, null=True, blank=True)
    record_length = models.PositiveIntegerField(default=0)
    header = models.CharField(max_length=512, null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_to = models.FileField()
    mapping = models.JSONField(default=dict())
    status = models.PositiveSmallIntegerField(default=UPLOADED, choices=STATUS_CHOICES)
    status_msg = models.CharField(max_length=256, null=True, blank=True)
    import_tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True, help_text="Tag all Members in this file")

    def __str__(self):
        return self.name

    def get_status_display(self):
        if self.status == self.CANCELED:
            return mark_safe('<span class="text-muted font-weight-bold">Canceled</span>')
        elif self.status == self.FAILED:
            return mark_safe('<span class="text-danger font-weight-bold" title="%s">Failed</span>' % self.status_msg.replace('"', '&quot;'))
        elif self.status == self.COMPLETE:
            return mark_safe('<span class="text-success font-weight-bold">Complete</span>')
        elif self.status == self.PROCESSING:
            return mark_safe('<span class="text-primary font-weight-bold">Processing</span>')
        elif self.status == self.PENDING:
            return mark_safe('<span class="text-info font-weight-bold">Ready</span>')
        elif self.status == self.UPLOADED:
            return mark_safe('<span class="text-savannah-orange font-weight-bold">Needs Mapping</span>')
        else:
            return mark_safe('<span class="text-muted font-weight-bold">%s</span>' % self.STATUS_NAMES[self.status])
    @property
    def columns(self):
        return [f.replace('"', '') for f in self.header.split(',')]

    def save(self, *args, **kwargs):
        header_lines = 1
        if self.header is None:
            self.header = self.uploaded_to.file.readline().decode(getattr(self.uploaded_to, 'encoding', 'utf-8')).strip().replace('"', '')
            header_lines = 0
        if self.mime_type is None and hasattr(self.uploaded_to.file, 'content_type'):
            self.mime_type = self.uploaded_to.file.content_type
        if self.record_length == 0:
            self.record_length = len(self.uploaded_to.file.readlines()) - header_lines
        super(UploadedFile, self).save(*args, **kwargs)

class Opportunity(models.Model):
    class Meta:
        verbose_name_plural = "Opportunities"
        # ordering = ("-created_at")
    REJECTED = -2
    DECLINED = -1
    IDENTIFIED = 0
    PROPOSED = 1
    AGREED = 2
    SUBMITTED = 3
    COMPLETE = 4
    CLOSED_STATUSES = (REJECTED, DECLINED, COMPLETE)
    STATUS_CHOICES = [
        (REJECTED, "Rejected"),
        (DECLINED, "Declined"),
        (IDENTIFIED, "Identified"),
        (PROPOSED, "Proposed"),
        (AGREED, "Agreed"),
        (SUBMITTED, "Submitted"),
        (COMPLETE, "Complete"),
        
    ]
    STATUS_MAP = dict(STATUS_CHOICES)
    STATUS_ICONS = {
        IDENTIFIED: 'fas fa-shield',
        PROPOSED: 'fas fa-shield-exclamation',
        AGREED: 'fas fa-shield-heart',
        SUBMITTED: 'fas fa-shield-plus',
        COMPLETE: 'fas fa-shield-check',
        DECLINED: 'fas fa-shield-minus',
        REJECTED: 'fas fa-shield-xmark',
    }
    STATUS_COLORS = {
        IDENTIFIED: 'secondary',
        PROPOSED: 'primary',
        AGREED: 'info',
        SUBMITTED: 'success',
        COMPLETE: 'success',
        DECLINED: 'danger',
        REJECTED: 'danger',
    }
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='opportunities')
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='opportunities')
    name = models.CharField(max_length=512)
    description = models.TextField()
    contribution_type = models.ForeignKey(ContributionType, on_delete=models.CASCADE, related_name='opportunities')
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True, related_name='opportunities')
    status = models.SmallIntegerField(choices=STATUS_CHOICES, default=IDENTIFIED)
    deadline = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='opportunities_created')
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='opportunities_closed')
    activities = models.ManyToManyField(Activity, null=True, blank=True, related_name='opportunities')

    @property
    def past_due(self):
        return self.deadline < datetime.datetime.utcnow()

    @property
    def is_done(self):
        return self.closed_at is not None

    def __str__(self):
        return self.name

    def get_next_options(self):
        options = []
        if self.status == self.IDENTIFIED:
            options = [
                self.PROPOSED,
                self.REJECTED,
            ]
        if self.status == self.PROPOSED:
            options = [
                self.AGREED,
                self.DECLINED,
            ]
        if self.status == self.AGREED:
            options = [
                self.SUBMITTED,
                self.DECLINED,
            ]
        if self.status == self.SUBMITTED:
            options = [
                self.COMPLETE,
                self.REJECTED,
            ]

        return [(self.STATUS_MAP[o], o, self.STATUS_ICONS[o], 'opportunity-%s' % self.STATUS_MAP[o].lower()) for o in options]

    @property
    def current_history(self):
        return self.history.filter(opportunity=self, ended_at__isnull=True).order_by('-started_at').first()

    def save(self, *args, **kwargs):
        r = super().save(*args, **kwargs)
        c = self.current_history
        if c is not None:
            if c.stage != self.status:
                c.ended_at = datetime.datetime.now()
                c.save()
                c = OpportunityHistory.objects.create(community=self.community, opportunity=self, stage=self.status, started_at=datetime.datetime.now())
        else:
            c = OpportunityHistory.objects.create(community=self.community, opportunity=self, stage=self.status, started_at=datetime.datetime.now())

class OpportunityHistory(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='history')
    stage = models.SmallIntegerField(choices=Opportunity.STATUS_CHOICES, default=Opportunity.IDENTIFIED)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
