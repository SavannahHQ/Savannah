from django.core.management.base import BaseCommand, CommandError
import operator
import json
import datetime, calendar
import dateutil.parser

from django.shortcuts import reverse
from django.db.models import F, Q, Count, Max, Min
from django.db.models.functions import Trunc
from django.core.serializers.json import DjangoJSONEncoder


from corm.models import *
from corm.models import Report, pluralize
from notifications.signals import notify


class Command(BaseCommand):
    help = 'Checks member activity and creates notifications for action'

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='date', type=str)
        parser.add_argument('--community', dest='community_id', type=int)

    def handle(self, *args, **options):
        for_date = options.get('date')
        community_id = options.get('community_id')
        self.verbosity = options.get('verbosity')

        if community_id:
            community = Community.objects.get(id=community_id)
            print("Using Community: %s" % community.name)
            communities = [community]
        else:
            communities = Community.objects.all()
        if for_date:
            self.tstamp = dateutil.parser.parse(for_date)
        else:
            self.tstamp = datetime.datetime.utcnow()

        for community in communities:
            self.make_growth_report(community)
            self.make_annual_report(community)

    def make_growth_report(self, community):
        month = datetime.datetime(self.tstamp.year, self.tstamp.month, 1, 0, 0, 0) - datetime.timedelta(days=1)
        start = datetime.datetime(month.year, month.month, 1, 0, 0, 0)
        end = datetime.datetime(self.tstamp.year, self.tstamp.month, 1, 23, 59, 59) - datetime.timedelta(days=1)

        reporter = GrowthReporter(community, start, end)
        reporter.verbosity = self.verbosity
        data = json.dumps(reporter.data(), cls=DjangoJSONEncoder)

        report, created = Report.objects.update_or_create(community=community, report_type=Report.GROWTH, generated=end, defaults={'title':"Monthly Report for %s %s" % (calendar.month_name[start.month], start.year), 'data':data})
        if created:
            recipients = community.managers or community.owner
            notify.send(report, 
                recipient=recipients, 
                verb="is ready in ",
                target=community,
                level='success',
                icon_name="fas fa-file-invoice",
                link=reverse('report_view', kwargs={'community_id': community.id, 'report_id':report.id})
            )

    def make_annual_report(self, community):
        year = self.tstamp.year - 1
        start = datetime.datetime(year, 1, 1, 0, 0, 0)
        end = datetime.datetime(year, 12, 31, 23, 59, 59)

        reporter = AnnualReporter(community, start, end)
        reporter.verbosity = self.verbosity
        data = json.dumps(reporter.data(), cls=DjangoJSONEncoder)

        report, created = Report.objects.update_or_create(community=community, report_type=Report.ANNUAL, generated=end + datetime.timedelta(days=1), defaults={'title':"Annual Report for %s" % start.year, 'data':data})
        if created:
            recipients = community.managers or community.owner
            notify.send(report, 
                recipient=recipients, 
                verb="is ready in ",
                target=community,
                level='success',
                icon_name="fas fa-file-invoice",
                link=reverse('report_view', kwargs={'community_id': community.id, 'report_id':report.id})
            )

class Reporter():

    def __init__(self, community, start, end):
        self.community = community
        self.start = start
        self.end = end
        self.verbosity = 0

    @property
    def time_range(self):
        return "year"

    def trunc_date(self, date):
        if self.time_range == "year":
            return str(date)[:7]
        elif self.time_range == "month":
            return str(date)[:10]
        else:
            return "%s %s:00" % (str(date)[:10], date.hour)

    @property
    def trunc_span(self):
        if self.time_range == "year":
            return "month"
        elif self.time_range == "month":
            return "day"
        else:
            return "hour"

    @property
    def timespan_chart_span(self):
        if self.time_range == "year":
            return 12
        elif self.time_range == "month":
            first, num = calendar.monthrange(self.start.year, self.start.month)
            return num
        else:
            first, num = calendar.monthrange(self.start.year, self.start.month)
            return num * 24

    def timespan_chart_keys(self, values):
        span_count = self.timespan_chart_span
        axis_values = []
        if self.trunc_span == "month":
            year = self.end.year
            month = self.end.month
            for i in range(span_count):
                axis_values.insert(0, "%04d-%02d" % (year, month))
                month -= 1
                if month < 1:
                    month = 12
                    year -= 1
            return axis_values
        elif self.trunc_span == "day":
            for i in range(span_count):
                day = self.trunc_date(self.end - datetime.timedelta(days=i))
                axis_values.insert(0, day)
            return axis_values
        elif self.trunc_span == "hour":
            for i in range(span_count):
                hour = self.trunc_date(self.end - datetime.timedelta(hours=i))
                axis_values.insert(0, hour)
            return axis_values
        else:
            return values[-span_count:]

class GrowthReporter(Reporter):

    @property
    def time_range(self):
        return "month"

    def data(self):
        return {
            'start': self.start,
            'end': self.end,
            'member_activity': self.get_member_activity(),
            'new_members': self.get_new_members(),
            'top_supporters': self.get_top_supporters(),
            'top_enablers': self.get_top_enablers(),
            'top_contributors': self.get_top_contributors(),
            'new_contributors': self.get_new_contributors(),
            'top_company_contributions': self.get_top_company_contributions(),
            'top_company_activity': self.get_top_company_activity(),
            'top_support_contributors': self.get_top_support_contributors(),
            'supporter_roles': self.get_supporter_roles(),
            'supported_by_member_tag': self.get_supported_by_member_tag(),
            'supported_companies': self.get_supported_companies(),
        }

    def get_top_support_contributors(self):
        members = Member.objects.filter(community=self.community)
        support_filter = Q(contribution__contribution_type__name='Support', contribution__timestamp__gte=self.start, contribution__timestamp__lte=self.end)
        members = members.annotate(contrib_count=Count('contribution', filter=support_filter)).filter(contrib_count__gt=0).order_by('-contrib_count')
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'contributions': member.contrib_count} for member in members[:20]]

    def get_supporter_roles(self):
        supporter_roles = {
            'community': 0,
            'staff': 0,
            'bot': 0
        }
        members = Member.objects.filter(community=self.community)
        support_filter = Q(contribution__contribution_type__name='Support', contribution__timestamp__gte=self.start, contribution__timestamp__lte=self.end)
        members = members.annotate(contrib_count=Count('contribution', filter=support_filter)).filter(contrib_count__gt=0).order_by('-contrib_count')
        for member in members:
            supporter_roles[member.role] += 1
        if self.verbosity >= 3:
            print("Roles: %s" % supporter_roles)
        return supporter_roles

    def get_supported_by_member_tag(self):
        tag_counts = dict()
        counted = set()
        supported = Participant.objects.filter(community=self.community, conversation__contribution__contribution_type__name="Support")
        supported = supported.filter(timestamp__gte=self.start, timestamp__lte=self.end)
        supported = supported.exclude(member=F('conversation__contribution__author'))
        for participant in supported:
            if participant.member.id in counted:
                continue
            counted.add(participant.member.id)
            for tag in participant.member.tags.all():
                if tag in tag_counts:
                    tag_counts[tag] += 1
                else:
                    tag_counts[tag] = 1
        if self.verbosity >= 3:
            print("Tags: %s" % tag_counts)
        return [{'tag_id': tag.id, 'tag_name': tag.name, 'tag_color': tag.color, 'count':count} for tag, count in sorted(tag_counts.items(), key=operator.itemgetter(1), reverse=True)]

    def get_supported_companies(self):
        company_counts = dict()
        supported = Participant.objects.filter(community=self.community, conversation__contribution__contribution_type__name="Support")
        supported = supported.filter(timestamp__gte=self.start, timestamp__lte=self.end)
        supported = supported.filter(member__company__isnull=False, member__company__is_staff=False)
        supported = supported.exclude(member=F('conversation__contribution__author'))
        for participant in supported:
            if participant.member.company in company_counts:
                company_counts[participant.member.company] += 1
            else:
                company_counts[participant.member.company] = 1
        if self.verbosity >= 3:
            print("Companies: %s" % company_counts)
        return [{'company_id': company.id, 'company_name': company.name, 'count':count} for company, count in sorted(company_counts.items(), key=operator.itemgetter(1), reverse=True)]

    def get_new_members(self):
        members = Member.objects.filter(community=self.community)
        members = members.filter(first_seen__gte=self.start, first_seen__lte=self.end).order_by('first_seen')
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'joined': member.first_seen} for member in members]

    def get_new_contributors(self):
        members = Member.objects.filter(community=self.community)
        members = members.annotate(first_contrib=Min('contribution__timestamp'))
        members = members.filter(first_contrib__gte=self.start, first_contrib__lte=self.end).order_by('first_contrib')
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'first_contrib': member.first_contrib} for member in members]

    def get_top_contributors(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__gte=self.start, contribution__timestamp__lte=self.end)

        members = members.annotate(contribution_count=Count('contribution', filter=contrib_filter)).filter(contribution_count__gt=0)
        for m in members:
            if m.contribution_count > 0:
                activity_counts[m] = m.contribution_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'contributions': count} for member, count in most_active[:20]]


    def get_top_supporters(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        convo_filter = Q(speaker_in__timestamp__gte=self.start, speaker_in__timestamp__lte=self.end)

        members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter)).filter(conversation_count__gt=0)
        for m in members:
            if m.conversation_count > 0:
                activity_counts[m] = m.conversation_count
        most_active = [(member, count) for member, count in sorted(activity_counts.items(), key=operator.itemgetter(1))]
        most_active.reverse()
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'conversations': count} for member, count in most_active[:20]]

    def get_top_enablers(self):
        members = Member.objects.filter(community=self.community)
        connection_filter = Q(memberconnection__last_connected__gte=self.start, memberconnection__last_connected__lte=self.end)
        members = members.annotate(connection_count=Count('connections', filter=connection_filter)).filter(connection_count__gt=0).prefetch_related('tags')
        connection_counts = dict()
        for m in members:
            if m.connection_count > 0:
                connection_counts[m] = m.connection_count
        most_connected = [(member, count) for member, count in sorted(connection_counts.items(), key=operator.itemgetter(1))]
        most_connected.reverse()
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'connections': count} for member, count in most_connected[:20]]

    def get_member_activity(self):
        months = list()
        joined = dict()
        active = dict()
        total = 0
        members = Member.objects.filter(community=self.community)

        seen = members.filter(first_seen__gte=self.start, first_seen__lte=self.end).annotate(month=Trunc('first_seen', self.trunc_span)).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
        for m in seen:
            total += 1
            month = self.trunc_date(m['month'])

            if month not in months:
                months.append(month)
            joined[month] = m['member_count']

        spoke = members.filter(speaker_in__timestamp__gte=self.start, speaker_in__timestamp__lte=self.end).annotate(month=Trunc('speaker_in__timestamp', self.trunc_span)).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
        for a in spoke:
            if a['month'] is not None:
                month = self.trunc_date(a['month'])

                if month not in months:
                    months.append(month)
                active[month] = a['member_count']
        months = self.timespan_chart_keys(sorted(months))
        return {
            'days': months, 
            'joined': [joined.get(month, 0) for month in months], 
            'active': [active.get(month, 0) for month in months], 
        }

    def get_top_company_contributions(self):
        contrib_filter = Q(member__contribution__timestamp__gte=self.start, member__contribution__timestamp__lte=self.end)
        companies = Company.objects.filter(community=self.community, is_staff=False).annotate(contrib_count=Count('member__contribution', filter=contrib_filter)).filter(contrib_count__gt=0).order_by('-contrib_count')
        companies = companies[:10]
        return [{'company_id': company.id, 'company_name': company.name, 'is_staff': company.is_staff, 'contributions':company.contrib_count} for company in companies]

    def get_top_company_activity(self):
        convo_filter = Q(member__speaker_in__timestamp__gte=self.start, member__speaker_in__timestamp__lte=self.end)
        companies = Company.objects.filter(community=self.community, is_staff=False).annotate(convo_count=Count('member__speaker_in', filter=convo_filter)).filter(convo_count__gt=0).order_by('-convo_count')
        companies = companies[:10]
        return [{'company_id': company.id, 'company_name': company.name, 'is_staff': company.is_staff, 'conversations':company.convo_count} for company in companies]

class AnnualReporter(Reporter):

    @property
    def time_range(self):
        return "year"

    def data(self):
        return {
            'start': self.start,
            'end': self.end,
            'member_activity': self.get_member_activity(),
            'counts': self.get_counts(),
            'conversation_sources': self.get_conversation_sources(),
            'contribution_types': self.get_contribution_types(),
            'top_supporters': self.get_top_supporters(),
            'top_contributors': self.get_top_contributors(),
        }

    def get_counts(self):
        counts = dict()
        conversations = Conversation.objects.filter(channel__source__community=self.community)
        conversations = conversations.filter(timestamp__gte=self.start, timestamp__lte=self.end)
        counts['conversations'] = conversations.count()
        contributions = Contribution.objects.filter(community=self.community)
        contributions = contributions.filter(timestamp__gte=self.start, timestamp__lte=self.end)
        counts['contributions'] = contributions.count()

        members = Member.objects.filter(community=self.community)
        counts['new_members'] = members.filter(first_seen__gte=self.start, first_seen__lte=self.end).count()
        members = members.annotate(first_contrib=Min('contribution__timestamp'))
        counts['new_contributors'] =  members.filter(first_contrib__gte=self.start, first_contrib__lte=self.end).count()
        return counts

    def get_conversation_sources(self):
        sources = Source.objects.filter(community=self.community)
        convo_filter = Q(channel__conversation__timestamp__gte=self.start, channel__conversation__timestamp__lte=self.end)

        sources = sources.annotate(conversation_count=Count('channel__conversation', filter=convo_filter)).filter(conversation_count__gt=0)

        return list(sources.values('name', 'connector', 'icon_name', 'conversation_count').order_by('-conversation_count'))

    def get_contribution_types(self):
        types = ContributionType.objects.filter(source__community=self.community).select_related('source')
        contrib_filter = Q(contribution__timestamp__gte=self.start, contribution__timestamp__lte=self.end)
        types = types.annotate(contribution_count=Count('contribution', filter=contrib_filter)).filter(contribution_count__gt=0)
        return list(types.values('name', 'source__name', 'source__connector', 'source__icon_name', 'contribution_count').order_by('-contribution_count'))

    def get_top_contributors(self):
        members = Member.objects.filter(community=self.community)
        contrib_filter = Q(contribution__timestamp__gte=self.start, contribution__timestamp__lte=self.end)

        members = members.annotate(contribution_count=Count('contribution', filter=contrib_filter)).filter(contribution_count__gt=0).order_by('-contribution_count')[:20]
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'contributions': member.contribution_count} for member in members]


    def get_top_supporters(self):
        activity_counts = dict()
        members = Member.objects.filter(community=self.community)
        convo_filter = Q(speaker_in__timestamp__gte=self.start, speaker_in__timestamp__lte=self.end)

        members = members.annotate(conversation_count=Count('speaker_in', filter=convo_filter)).filter(conversation_count__gt=0).order_by('-conversation_count')[:20]
        return [{'member_id': member.id, 'member_name': member.name, 'member_role':member.role, 'conversations': member.conversation_count} for member in members]

    def get_member_activity(self):
        months = list()
        joined = dict()
        active = dict()
        total = 0
        members = Member.objects.filter(community=self.community)

        seen = members.filter(first_seen__gte=self.start, first_seen__lte=self.end).annotate(month=Trunc('first_seen', self.trunc_span)).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
        for m in seen:
            total += 1
            month = self.trunc_date(m['month'])

            if month not in months:
                months.append(month)
            joined[month] = m['member_count']

        spoke = members.filter(speaker_in__timestamp__gte=self.start, speaker_in__timestamp__lte=self.end).annotate(month=Trunc('speaker_in__timestamp', self.trunc_span)).values('month').annotate(member_count=Count('id', distinct=True)).order_by('month')
        for a in spoke:
            if a['month'] is not None:
                month = self.trunc_date(a['month'])

                if month not in months:
                    months.append(month)
                active[month] = a['member_count']
        months = self.timespan_chart_keys(sorted(months))
        return {
            'months': months, 
            'joined': [joined.get(month, 0) for month in months], 
            'active': [active.get(month, 0) for month in months], 
        }
