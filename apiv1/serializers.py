import datetime
import hashlib
from collections import OrderedDict
from rest_framework import serializers

from corm.models import Source, Channel, Member, Contact, Conversation, Contribution, ContributionType, Tag
from corm.plugins import PluginImporter
from django.db import models

def update_source(source):
    source.last_import = datetime.datetime.utcnow()
    source.save()

def update_channel(channel):
    channel.last_import = datetime.datetime.utcnow()
    channel.save()
    update_source(channel.source)

def django_field_value(instance, field_name):
    print("Looking up %s in %s" % (field_name, instance))
    field_stack = field_name.split('__')
    for field_name in field_stack[:-1]:
        instance = getattr(instance, field_name)
    print("Returning %s from %s" % (field_stack[-1], instance))
    return getattr(instance, field_stack[-1])

class SourceSerializer(serializers.Serializer):
    community = serializers.CharField(max_length=256, required=False, allow_null=True)
    name = serializers.CharField(max_length=256, required=False, allow_null=True)
    icon_name = serializers.CharField(max_length=256, required=False, allow_null=True)
    first_import = serializers.DateTimeField()
    last_import = serializers.DateTimeField()
    enabled = serializers.BooleanField()


class TagsField(serializers.Field):
    def __init__(self, through=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.through = through

    def get_attribute(self, instance):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        if isinstance(instance, OrderedDict):
            return instance.get(self.source)

        if self.through and hasattr(instance, self.through):
            instance = getattr(instance, self.through)
        return [tag.name for tag in getattr(instance, self.source).all()]

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if isinstance(data, str):
            return [data]
        if isinstance(data, list):
            return data
        raise serializers.ValidationError('Invalid value for %s. Must be an array or string' % self.source)

class ImportedModelRelatedField(serializers.Field):
    def __init__(self, model, source_from=None, related_field=None, many=False, *args, **kwargs):
        self.model = model
        self.related_field = related_field
        self.many = many
        self.source_from = source_from
        self.corm_source = None
        super().__init__(*args, **kwargs)

    def get_attribute(self, instance):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        if self.source_from:
            if self.source_from == 'self':
                self.corm_source = instance.source
            else:
                self.corm_source = getattr(instance, self.source_from).source
        else:
            self.corm_source = getattr(instance, self.source).source
        try:
            return getattr(instance, self.source)
        except:
            return None

    def to_representation(self, value):
        if self.related_field:
            try:
                if self.many:
                    lookup = {'%s__in'%self.related_field: value.all(), 'source':self.corm_source}
                    return [obj.origin_id for obj in self.model.objects.filter(**lookup)]
                else:
                    lookup = {self.related_field: value, 'source':self.corm_source}
                    obj = self.model.objects.get(**lookup)
                    return obj.origin_id
            except self.model.DoesNotExist:
                return None
        if self.many:
            return [child.origin_id for child in value.all()]
        return value.origin_id

    def to_internal_value(self, data):
        return data

class ZapierIDField(serializers.Field):
    def __init__(self, id_field='origin_id', tstamp_field='timestamp', many=False, *args, **kwargs):
        self.id_field = id_field
        self.tstamp_field = tstamp_field
        self.many = many
        super().__init__(*args, **kwargs)

    def get_attribute(self, instance):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        id_value = django_field_value(instance, self.id_field)
        tstamp_value = django_field_value(instance, self.tstamp_field)
        hash_value = hashlib.md5()
        hash_value.update(str(id_value).encode('utf-8'))
        hash_value.update(str(tstamp_value).encode('utf-8'))
        return hash_value.hexdigest()

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        return data

class IdentitySerializer(serializers.Serializer):
    origin_id = serializers.CharField(max_length=256)
    username = serializers.CharField(source='detail', max_length=256)
    name = serializers.CharField(max_length=256, required=False, allow_null=True)
    email = serializers.EmailField(source='email_address', required=False, allow_null=True)
    avatar = serializers.URLField(source='avatar_url', required=False, allow_null=True)
    tags = TagsField(through='member', required=False)

    def save(self, source):
        importer = PluginImporter(source)
        member = importer.make_member(
            origin_id=self.validated_data.get('origin_id'), 
            detail=self.validated_data.get('detail'), 
            email_address=self.validated_data.get('email_address'), 
            avatar_url=self.validated_data.get('avatar_url'), 
            name=self.validated_data.get('name', self.validated_data.get('detail'))
        )

        for tag_name in self.validated_data.get('tags', []):
            tag, created = Tag.objects.get_or_create(community=source.community, name=tag_name, defaults={
                'color': 'E5E6E8'
            })
            member.tags.add(tag)

        update_source(source)
        return Contact.objects.get(source=source, member=member)

class ZapierIdentitySerializer(serializers.Serializer):
    id = ZapierIDField(id_field='origin_id', tstamp_field='member__first_seen')
    origin_id = serializers.CharField(max_length=256)
    username = serializers.CharField(source='detail', max_length=256)
    name = serializers.CharField(max_length=256, required=False, allow_null=True)
    email = serializers.EmailField(source='email_address', required=False, allow_null=True)
    avatar = serializers.URLField(source='avatar_url', required=False, allow_null=True)


def get_or_create_member(source, origin_id):
    try:
        identity = Contact.objects.get(origin_id=origin_id, source=source)
        member = identity.member
    except Contact.DoesNotExist:
        member = Member.objects.create(
            name=origin_id, 
            community=source.community, 
            first_seen=datetime.datetime.utcnow(),
            last_seen=datetime.datetime.utcnow(),
        )
        identity = Contact.objects.create(
            member = member,
            source = source,
            origin_id = origin_id,
            detail = origin_id,
        )
    return member

def get_or_create_channel(source, origin_id):
    try:
        channel = Channel.objects.get(origin_id=origin_id, source=source)
    except Channel.DoesNotExist:
        channel = Channel.objects.create(
            origin_id = origin_id,
            name = origin_id,
            source = source,
        )
    return channel

class ConversationSerializer(serializers.Serializer):
    origin_id = serializers.CharField(max_length=256)
    speaker = ImportedModelRelatedField(model=Contact, related_field='member', source_from='channel')
    channel = ImportedModelRelatedField(model=Channel)
    timestamp = serializers.DateTimeField()
    content = serializers.CharField(allow_null=True)
    location = serializers.URLField(required=False, allow_null=True)
    participants = ImportedModelRelatedField(model=Contact, related_field='member', source_from='channel', many=True, required=False)
    tags = TagsField(required=False)

    def save(self, source):
        # Get or create speaker Member and Contact
        importer = PluginImporter(source)
        # Get or create Channel
        channel = get_or_create_channel(origin_id=self.validated_data.get('channel'), source=source)

        speaker = importer.make_member(
            origin_id=self.validated_data.get('speaker'), 
            detail=self.validated_data.get('speaker'),
            channel=channel,
            tstamp=self.validated_data.get('timestamp'), 
            speaker=True,
        )

        convo = importer.make_conversation(
            origin_id=self.validated_data.get('origin_id'), 
            channel=channel, 
            speaker=speaker, 
            content=self.validated_data.get('content'), 
            tstamp=self.validated_data.get('timestamp'), 
            location=self.validated_data.get('location'), 
            thread=None
        )

        participants = set()
        participants.add(speaker)
        for participant_origin_id in self.validated_data.get('participants', []):
            participant = importer.make_member(
                origin_id=participant_origin_id, 
                detail=participant_origin_id,
                tstamp=self.validated_data.get('timestamp'), 
                )
            participants.add(participant)
        importer.add_participants(convo, participants)

        for tag_name in self.validated_data.get('tags', []):
            tag, created = Tag.objects.get_or_create(community=source.community, name=tag_name, defaults={
                'color': 'E5E6E8'
            })
            convo.tags.add(tag)

        update_channel(channel)
        return convo

def get_or_create_contrib_type(source, name):
    try:
        contribution_type = ContributionType.objects.get(name=name, source=source)
    except ContributionType.DoesNotExist:
        contribution_type = ContributionType.objects.create(
            community = source.community,
            source = source,
            name = name,
        )
    return contribution_type

class ContributionSerializer(serializers.Serializer):
    origin_id = serializers.CharField(max_length=256)
    author = ImportedModelRelatedField(model=Contact, related_field='member', source_from='channel')
    contribution_type = serializers.CharField(allow_null=False)
    channel = ImportedModelRelatedField(model=Channel)
    timestamp = serializers.DateTimeField()
    title = serializers.CharField(allow_null=False)

    location = serializers.URLField(required=False, allow_null=True)
    conversation = ImportedModelRelatedField(Conversation, source_from='channel', required=False, allow_null=True)
    tags = TagsField(required=False)

    def save(self, source):
        # Get or create speaker Member and Contact
        importer = PluginImporter(source)
        # Get or create Channel
        channel = get_or_create_channel(origin_id=self.validated_data.get('channel'), source=source)

        author = importer.make_member(
            origin_id=self.validated_data.get('author'), 
            detail=self.validated_data.get('author'),
            channel=channel,
            tstamp=self.validated_data.get('timestamp'), 
            speaker=True,
        )

        # Get or create contribution type
        contribution_type = get_or_create_contrib_type(name=self.validated_data.get('contribution_type'), source=source)

        # Get converasation if it exists
        conversation=None
        if self.validated_data.get('conversation', None):
            try:
                conversation = Conversation.objects.get(channel__source=source, origin_id=self.validated_data.get('conversation'))
            except Exception as e:
                pass

        contrib, created = Contribution.objects.update_or_create(
            origin_id=self.validated_data.get('origin_id'), 
            community=source.community, 
            defaults={
                'contribution_type':contribution_type, 
                'channel':channel, 
                'author':author, 
                'timestamp':self.validated_data.get('timestamp'), 
                'title':self.validated_data.get('title'), 
                'location':self.validated_data.get('location'),
                'conversation':conversation
            }
        )

        for tag_name in self.validated_data.get('tags', []):
            tag, created = Tag.objects.get_or_create(community=source.community, name=tag_name, defaults={
                'color': 'E5E6E8'
            })
            contrib.tags.add(tag)

        update_channel(channel)
        return contrib

