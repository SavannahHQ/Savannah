from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from corm.models import Community, Company


class CompanyLogoTests(TestCase):

    def setUp(self):
        owner = User.objects.create_user('owner', 'owner@example.com', 'pw')
        self.community = Community.objects.create(name='Acme', owner=owner)

    def company(self, **kwargs):
        return Company.objects.create(community=self.community, name='Acme', **kwargs)

    def test_domain_from_website(self):
        self.assertEqual(self.company(website='https://www.example.com/about?x=1').domain, 'example.com')
        self.assertEqual(self.company(website='http://Example.com:8080').domain, 'example.com')
        self.assertEqual(self.company(website='example.com').domain, 'example.com')
        self.assertIsNone(self.company(website='').domain)
        self.assertIsNone(self.company().domain)

    @override_settings(COMPANY_LOGO_URL='https://icons.duckduckgo.com/ip3/%(domain)s.ico')
    def test_logo_url_derived_from_domain_without_saving(self):
        company = self.company(website='https://www.example.com/')
        self.assertEqual(company.logo_url, 'https://icons.duckduckgo.com/ip3/example.com.ico')
        company.refresh_from_db()
        self.assertIsNone(company.icon_url)

    @override_settings(COMPANY_LOGO_URL='https://www.google.com/s2/favicons?domain=%(domain)s&sz=64')
    def test_logo_url_follows_configured_provider(self):
        company = self.company(website='https://example.com')
        self.assertEqual(company.logo_url, 'https://www.google.com/s2/favicons?domain=example.com&sz=64')

    @override_settings(COMPANY_LOGO_URL='https://icons.duckduckgo.com/ip3/%(domain)s.ico')
    def test_explicit_icon_url_wins(self):
        company = self.company(website='https://example.com', icon_url='https://cdn.example.com/logo.png')
        self.assertEqual(company.logo_url, 'https://cdn.example.com/logo.png')

    @override_settings(COMPANY_LOGO_URL='')
    def test_logo_url_disabled(self):
        self.assertIsNone(self.company(website='https://example.com').logo_url)

    def test_no_website_no_logo(self):
        self.assertIsNone(self.company().logo_url)
