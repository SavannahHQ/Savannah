import enum
from django.core.management.base import BaseCommand, CommandError
import datetime
import re
import subprocess
import requests
import csv
import random
from io import TextIOWrapper
from time import sleep
from corm.models import Community, Member, Contact, Company, Tag, UploadedFile
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
            f = TextIOWrapper(upload.uploaded_to)
            reader = csv.reader(f)
            headers = reader.__next__()
            columns = dict()
            for i, header in enumerate(headers):
                columns[header] = i
            print(columns)
            for record in reader:
                member = Member(community=upload.community, first_seen=datetime.datetime.utcnow())
                for c, field in upload.mapping.items():
                    if field:
                        if self.verbosity >= 3:
                            print("%s = %s" % (field, record[columns[c]]))

                        if field == 'origin_id':
                            self.process_origin_field(member, upload.source, record[columns[c]])
                        elif field == 'company':
                            self.process_company_field(member, field, record[columns[c]])
                        elif field == 'tags':
                            self.process_tags_field(member, field, record[columns[c]])
                        else:
                            self.process_char_field(member, field, record[columns[c]])

                if self.verbosity >= 3:
                    print(member)
                member.save()
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

    def process_origin_field(self, member, source, value):
        if source is None:
            raise RuntimeError("Can not map Origin ID field because no the import has no Source assigned.")
        if not member.id:
            member.save()
        identity, created = Contact.objects.get_or_create(source=source, member=member, origin_id=value, detail=value, name=value)

    def process_company_field(self, member, field, value):
        if not member.id:
            member.save()
        companies = Company.objects.filter(community=member.community, name=value)
        if len(companies) == 0:
            company = Company.objects.create(community=member.community, name=value)
        else:
            company = companies.first()
        setattr(member, field, company)

    def process_tags_field(self, member, field, value):
        if not member.id:
            member.save()
        tag_names = [t.strip() for t in value.split(',')]
        for t in tag_names:
            tag, created = Tag.objects.get_or_create(community=member.community, name=t, defaults={'color': random_tag_color()})
            member.tags.add(tag)

    def process_char_field(self, member, field, value):
        if getattr(member, field):
            setattr(member, field, getattr(member, field)+' '+value)
        else:
            setattr(member, field, value)