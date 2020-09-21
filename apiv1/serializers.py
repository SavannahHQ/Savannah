import datetime
from rest_framework import serializers

from corm.models import Source, Channel, Member, Contact, Conversation, Contribution
from corm.plugins import PluginImporter

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
            self.corm_source = getattr(instance, self.source_from).source
        else:
            self.corm_source = getattr(instance, self.source).source
        return getattr(instance, self.source)

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

class IdentitySerializer(serializers.Serializer):
    origin_id = serializers.CharField(max_length=256)
    username = serializers.CharField(source='detail', max_length=256)
    name = serializers.CharField(max_length=256, required=False, allow_null=True)
    email = serializers.EmailField(source='email_address', required=False, allow_null=True)
    avatar = serializers.URLField(source='avatar_url', required=False, allow_null=True)

    def save(self, source):
        importer = PluginImporter(source)
        member = importer.make_member(
            origin_id=self.validated_data.get('origin_id'), 
            detail=self.validated_data.get('detail'), 
            email_address=self.validated_data.get('email_address'), 
            avatar_url=self.validated_data.get('avatar_url'), 
            name=self.validated_data.get('name', self.validated_data.get('detail'))
        )
        return Contact.objects.get(source=source, member=member)


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
    participants = ImportedModelRelatedField(model=Contact, related_field='member', source_from='channel', many=True)

    def save(self, source):
        # Get or create speaker Member and Contact
        importer = PluginImporter(source)
        speaker = importer.make_member(
            origin_id=self.validated_data.get('speaker'), 
            detail=self.validated_data.get('speaker'),
            tstamp=self.validated_data.get('timestamp'), 
        )

        # Get or create Channel
        channel = get_or_create_channel(origin_id=self.validated_data.get('channel'), source=source)

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
        for participant_origin_id in self.validated_data.get('participants'):
            participant = importer.make_member(
                origin_id=participant_origin_id, 
                detail=participant_origin_id,
                tstamp=self.validated_data.get('timestamp'), 
                )
            speaker.add_connection(participant, source, self.validated_data.get('timestamp'))
            participants.add(participant)
        convo.participants.set(participants)

        return convo

