import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from corm.models import Community, Source, Channel, Member, Contact, Conversation, Contribution, Participant
from corm.plugins import linear
from corm.plugins.linear import LinearImporter, LinearPlugin, graphql, auth_header, LinearAPIError


def user(uid, name, display=None, email=None):
    return {
        'id': uid,
        'name': name,
        'displayName': display or name.lower().replace(' ', ''),
        'email': email,
        'avatarUrl': 'https://img.example/%s.png' % uid,
        'url': 'https://linear.app/acme/profiles/%s' % (display or name.lower()),
    }


ALICE = user('u-alice', 'Alice Example', 'alice', 'alice@example.com')
BOB = user('u-bob', 'Bob Example', 'bob')

ISSUES_PAGE_1 = {
    'issues': {
        'nodes': [
            {
                'id': 'iss-1', 'identifier': 'ACM-1', 'title': 'Login broken',
                'description': 'Cannot log in with SSO',
                'url': 'https://linear.app/acme/issue/ACM-1',
                'createdAt': '2026-09-01T10:00:00.000Z', 'updatedAt': '2026-09-03T10:00:00.000Z',
                'completedAt': '2026-09-03T09:00:00.000Z',
                'creator': ALICE, 'assignee': BOB,
                'comments': {'nodes': [
                    {'id': 'cmt-1', 'body': 'Looking into it', 'url': 'https://linear.app/acme/issue/ACM-1#cmt-1',
                     'createdAt': '2026-09-02T10:00:00.000Z', 'user': BOB},
                    {'id': 'cmt-bot', 'body': 'Linked PR', 'url': None,
                     'createdAt': '2026-09-02T11:00:00.000Z', 'user': None},
                ]},
            },
        ],
        'pageInfo': {'hasNextPage': True, 'endCursor': 'cursor-1'},
    }
}
ISSUES_PAGE_2 = {
    'issues': {
        'nodes': [
            {
                'id': 'iss-2', 'identifier': 'ACM-2', 'title': 'Add dark mode', 'description': None,
                'url': 'https://linear.app/acme/issue/ACM-2',
                'createdAt': '2026-09-05T10:00:00Z', 'updatedAt': '2026-09-05T10:00:00Z',
                'completedAt': None, 'creator': BOB, 'assignee': None,
                'comments': {'nodes': []},
            },
            {
                # Created by an integration: no creator, should be skipped without error
                'id': 'iss-3', 'identifier': 'ACM-3', 'title': 'Automated', 'description': None,
                'url': 'https://linear.app/acme/issue/ACM-3',
                'createdAt': '2026-09-06T10:00:00.000Z', 'updatedAt': '2026-09-06T10:00:00.000Z',
                'completedAt': None, 'creator': None, 'assignee': None,
                'comments': {'nodes': []},
            },
        ],
        'pageInfo': {'hasNextPage': False, 'endCursor': None},
    }
}


def fake_api(*pages):
    """Return a graphql() stand-in that serves issue pages in order and answers user lookups."""
    pages = list(pages)
    users = {u['id']: u for u in (ALICE, BOB)}

    def _call(token, query, variables=None, **kwargs):
        if query is linear.USER_QUERY:
            return {'user': users.get(variables['id'])}
        if query is linear.ISSUES_QUERY:
            return pages.pop(0)
        raise AssertionError('unexpected query: %s' % query[:40])
    return _call


class LinearPluginTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@example.com', 'pw')
        self.community = Community.objects.create(name='Acme', owner=self.owner)
        self.source = Source.objects.create(
            community=self.community, connector='corm.plugins.linear', name='Acme',
            server='https://linear.app/acme', auth_id='acme', auth_secret='lin_api_test')
        self.channel = Channel.objects.create(source=self.source, name='Engineering (ENG)', origin_id='team-1')

    def test_auth_header(self):
        self.assertEqual(auth_header('lin_api_abc'), 'lin_api_abc')
        self.assertEqual(auth_header('oauth-token'), 'Bearer oauth-token')

    @mock.patch('corm.plugins.linear.requests.post')
    def test_graphql_raises_on_errors(self, post):
        post.return_value = mock.Mock(status_code=200, json=lambda: {'errors': [{'message': 'Bad key'}]})
        with self.assertRaises(LinearAPIError):
            graphql('lin_api_x', '{ viewer { id } }')
        post.return_value = mock.Mock(status_code=401, text='')
        with self.assertRaises(LinearAPIError):
            graphql('lin_api_x', '{ viewer { id } }')

    @mock.patch('corm.plugins.linear.graphql')
    def test_get_channels_lists_teams(self, gql):
        gql.return_value = {'teams': {
            'nodes': [{'id': 'team-1', 'key': 'ENG', 'name': 'Engineering', 'description': 'Builds things', 'private': False}],
            'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
        channels = LinearPlugin().get_channels(self.source)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]['id'], 'team-1')
        self.assertEqual(channels[0]['name'], 'Engineering (ENG)')
        self.assertEqual(channels[0]['topic'], 'Builds things')

    @mock.patch('corm.plugins.linear.graphql')
    def test_import_channel(self, gql):
        gql.side_effect = fake_api(ISSUES_PAGE_1, ISSUES_PAGE_2)
        importer = LinearImporter(self.source)
        from_date = datetime.datetime(2026, 8, 1)
        importer.import_channel(self.channel, from_date)

        # Paginated: two issue queries, the second carrying the cursor; no per-user lookups needed
        issue_calls = [c for c in gql.call_args_list if c.args[1] is linear.ISSUES_QUERY]
        self.assertEqual(len(issue_calls), 2)
        self.assertEqual(issue_calls[0].args[2]['since'], '2026-08-01T00:00:00.000000Z')
        self.assertEqual(issue_calls[1].args[2]['after'], 'cursor-1')
        self.assertEqual(len(issue_calls), gql.call_count)

        # Two humans became members; bot comment and creator-less issue were ignored
        self.assertEqual(Member.objects.filter(community=self.community).count(), 2)
        alice = Contact.objects.get(origin_id='linear.app/u-alice')
        self.assertEqual(alice.detail, 'alice')
        self.assertEqual(alice.email_address, 'alice@example.com')
        self.assertEqual(alice.member.name, 'Alice Example')

        # Issue + its human comment + second issue = 3 conversations
        self.assertEqual(Conversation.objects.filter(channel=self.channel).count(), 3)
        issue_convo = Conversation.objects.get(origin_id='iss-1')
        self.assertTrue(issue_convo.content.startswith('Login broken'))
        self.assertIn('Cannot log in with SSO', issue_convo.content)
        self.assertEqual(issue_convo.location, 'https://linear.app/acme/issue/ACM-1')
        comment = Conversation.objects.get(origin_id='cmt-1')
        self.assertEqual(comment.thread_start, issue_convo)
        self.assertEqual(comment.speaker.name, 'Bob Example')
        self.assertFalse(Conversation.objects.filter(origin_id='cmt-bot').exists())

        # Completed issue is a Contribution by the assignee
        contrib = Contribution.objects.get(origin_id='iss-1')
        self.assertEqual(contrib.contribution_type.name, 'Completed Issue')
        self.assertEqual(contrib.author.name, 'Bob Example')
        self.assertEqual(contrib.title, 'ACM-1 Login broken')
        self.assertEqual(contrib.timestamp.replace(tzinfo=None), datetime.datetime(2026, 9, 3, 9, 0))
        self.assertFalse(Contribution.objects.filter(origin_id='iss-2').exists())

        # Creator, assignee and commenter all participate in the issue thread
        participants = set(Participant.objects.filter(conversation=issue_convo).values_list('member__name', flat=True))
        self.assertEqual(participants, {'Alice Example', 'Bob Example'})

        # Timestamps without milliseconds are tolerated
        self.assertEqual(Conversation.objects.get(origin_id='iss-2').timestamp.replace(tzinfo=None), datetime.datetime(2026, 9, 5, 10, 0))

    @mock.patch('corm.plugins.linear.graphql')
    def test_import_is_idempotent(self, gql):
        gql.side_effect = fake_api(ISSUES_PAGE_1, ISSUES_PAGE_2, ISSUES_PAGE_1, ISSUES_PAGE_2)
        importer = LinearImporter(self.source)
        importer.import_channel(self.channel, datetime.datetime(2026, 8, 1))
        importer.import_channel(self.channel, datetime.datetime(2026, 8, 1))
        self.assertEqual(Conversation.objects.filter(channel=self.channel).count(), 3)
        self.assertEqual(Contribution.objects.filter(community=self.community).count(), 1)
        self.assertEqual(Member.objects.filter(community=self.community).count(), 2)

    @mock.patch('corm.plugins.linear.graphql')
    def test_update_source_fills_workspace(self, gql):
        gql.return_value = {'viewer': dict(ALICE, organization={'id': 'org', 'name': 'Acme Inc', 'urlKey': 'acme-inc'})}
        source = Source.objects.create(community=self.community, connector='corm.plugins.linear', name='x',
                                       server='https://linear.app', auth_secret='lin_api_test')
        LinearImporter(source).update_source()
        source.refresh_from_db()
        self.assertEqual(source.auth_id, 'acme-inc')
        self.assertEqual(source.server, 'https://linear.app/acme-inc')

    def test_identity_url(self):
        now = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        member = Member.objects.create(community=self.community, name='Alice', first_seen=now, last_seen=now)
        contact = Contact.objects.create(member=member, source=self.source, origin_id='linear.app/u-alice', detail='alice')
        self.assertEqual(LinearPlugin().get_identity_url(contact), 'https://linear.app/acme/profiles/alice')
