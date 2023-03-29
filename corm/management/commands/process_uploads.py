import enum
from django.core.management.base import BaseCommand, CommandError
from django.db.models.fields import CharField
import datetime
import dateutil.parser as timestamp_parser
import re
import subprocess
import requests
import csv
import random
from io import TextIOWrapper
from time import sleep, strptime
from corm.models import Community, Member, Contact, Company, Tag, UploadedFile, Event, EventAttendee, Note
from corm import colors


def random_tag_color(community=None):
    try:
        if community:
            used_colors = set(Tag.objects.filter(community=community).values('color').distinct().values_list('color', flat=True))
            available_colors = list(set(colors.TAG_COLORS) - used_colors)
            return available_colors[random.randrange(len(available_colors))]
        else:
            return colors.TAG_COLORS[random.randrange(len(colors.TAG_COLORS))]
    except:
        return colors.OTHER

class Command(BaseCommand):
    help = 'Import data from sources'

    def add_arguments(self, parser):
        parser.add_argument('--community', dest='community_id', type=int)
        parser.add_argument('--file', dest='upload_id', type=int)
        parser.add_argument('--debug', dest='debug', action='store_true', help='Enter debugger on errors')
        parser.add_argument('--limit', dest='limit', type=int, help='Number of possible files to import')

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity')
        community_id = options.get('community_id')
        upload_id = options.get('upload_id')
        self.debug = options.get('debug')
        limit = options.get('limit')

        self.import_timestamp = datetime.datetime.utcnow()

        uploads = UploadedFile.objects.filter(status=UploadedFile.PENDING)

        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            uploads = uploads.filter(community=community)

        if upload_id:
            upload = UploadedFile.objects.get(id=upload_id)
            print("Using Upload: %s" % upload.name)
            uploads = uploads.filter(id=upload.id)

        count = 0
        for upload in uploads:
            if limit and count >= limit:
                break
            print("Processing %s..." % upload, end=None)
            status = self.process_upload(upload)
            print(status)

    def process_upload(self, upload):
        upload.status = UploadedFile.PROCESSING
        upload.save()

        try:
            f = TextIOWrapper(upload.uploaded_to.file)
            if self.verbosity >= 3:
                print("Opening file in CSV reader...")
            reader = csv.reader(f)
            if self.verbosity >= 3:
                print("Reading headers...")
            headers = reader.__next__()
            columns = dict()
            for i, header in enumerate(headers):
                columns[header] = i
            if self.verbosity >= 3:
                print("Headers:")
                print(columns)
            origin_id_column = None
            if upload.source:
                for c, field in upload.mapping.items():
                    if field == 'origin_id':
                        origin_id_column = columns[c]
                        break
            if self.verbosity >= 3:
                print("Reading data...")
            for record in reader:
                if self.verbosity >= 3:
                    print("Line: %s"%record)
                member = Member(community=upload.community, first_seen=datetime.datetime.utcnow())
                if upload.source and origin_id_column is not None:
                    member = self.get_member_by_origin(upload.source, record[origin_id_column])
                managed_fields = {}
                for c, field in upload.mapping.items():
                    if field:
                        if self.verbosity >= 3:
                            print("%s = %s" % (field, record[columns[c]]))

                        if field == 'origin_id':
                            pass
                        elif field == 'company':
                            self.process_company_field(member, field, record[columns[c]])
                        elif field == 'tags':
                            self.process_tags_field(member, record[columns[c]])
                        elif field == 'first_seen' or field == 'last_seen':
                            self.process_timestamp_field(member, field, record[columns[c]])
                        elif field == 'first_name':
                            self.process_char_field(member, 'name', record[columns[c]], prepend=True)
                        elif field == 'last_name':
                            self.process_char_field(member, 'name', record[columns[c]], prepend=False)
                        elif field == 'note':
                            self.process_note_field(member, record[columns[c]], author=upload.uploaded_by)
                        else:
                            if field not in managed_fields:
                                managed_fields[field] = not getattr(member, field)
                            if managed_fields[field]:
                                self.process_char_field(member, field, record[columns[c]])

                if self.verbosity >= 3:
                    print(member)
                    print()
                member.save()
                if upload.event is not None:
                    a, created = EventAttendee.objects.get_or_create(community=upload.event.community, event=upload.event, member=member, defaults={'timestamp':upload.event.start_timestamp, 'role':EventAttendee.GUEST})
                    if created:
                        a.update_activity()
                        if upload.event.start_timestamp < member.first_seen:
                            member.first_seen = upload.event.start_timestamp
                        if member.last_seen is None or upload.event.start_timestamp > member.last_seen:
                            member.last_seen = upload.event.start_timestamp
                        member.save()
                if upload.import_tag is not None:
                    member.tags.add(upload.import_tag)
        except Exception as e:
            print(e)
            if self.debug:
                import pdb; pdb.set_trace()
            upload.status = UploadedFile.FAILED
            upload.status_msg = str(e)
            upload.save()
            return "Failed"

        upload.status = UploadedFile.COMPLETE
        upload.save()
        return "Complete"

    def get_member_by_origin(self, source, origin_id):
        if source is None:
            raise RuntimeError("Can not map Origin ID field because no the import has no Source assigned.")
        try:
            identity = Contact.objects.get(source=source, origin_id=origin_id)
            if self.verbosity >= 3:
                print("Found identity for %s" % origin_id)
            return identity.member
        except:
            if self.verbosity >= 3:
                print("Creating new identity for %s" % origin_id)
            member = Member.objects.create(community=source.community, first_seen=datetime.datetime.utcnow())
            identity, created = Contact.objects.get_or_create(source=source, member=member, origin_id=origin_id, detail=origin_id, name=origin_id)
            return member

    def process_company_field(self, member, field, value):
        if not member.id:
            member.save()
        companies = Company.objects.filter(community=member.community, name=value)
        if len(companies) == 0:
            company = Company.objects.create(community=member.community, name=value)
        else:
            company = companies.first()
        setattr(member, field, company)

    def process_tags_field(self, member, value):
        if not member.id:
            member.save()
        tag_names = [t.strip() for t in value.split(',')]
        for t in tag_names:
            tag, created = Tag.objects.get_or_create(community=member.community, name=t, defaults={'color': random_tag_color()})
            member.tags.add(tag)

    def process_note_field(self, member, value, author):
        if not value:
            return
        if not member.id:
            member.save()
        try:
            note = Note.objects.get(member=member, timestamp=self.import_timestamp, author=author)
            created = False
        except Note.DoesNotExist:
            note = Note.objects.create(member=member, timestamp=self.import_timestamp, author=author, content=value)
            created = True
        if created and self.verbosity >= 2:
            print("New note created for '%s' at %s" % (value, self.import_timestamp))
        if created:
            note.timestamp = timestamp=self.import_timestamp
        else:
            note.content += '\n'+value
        note.save()

    def process_char_field(self, member, field_name, value, prepend=False):
        field = member._meta.get_field(field_name)
        if isinstance(field, CharField):
            value = value[:field.max_length]
            try:
                if getattr(member, field_name):
                    if prepend:
                        setattr(member, field_name, value+' '+getattr(member, field_name))
                    else:
                        setattr(member, field_name, getattr(member, field_name)+' '+value)
                else:
                    setattr(member, field_name, value)
            except Exception as e:
                raise RuntimeError("Error setting field %s to '%s'. %s" % (field_name, value, str(e)))

    def process_timestamp_field(self, member, field_name, value):
        try:
            value = timestamp_parser.parse(value)
        except:
            raise RuntimeError("Unknown timestamp format: %s" % value)

        setattr(member, field_name, value)
        if field_name == 'first_seen' and (member.last_seen is None or value > member.last_seen):
            member.last_seen = value
        if field_name == 'last_seen' and (member.first_seen is None or value < member.first_seen):
            member.first_seen = value