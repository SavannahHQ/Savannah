from corm.plugins import BasePlugin, PluginImporter
import datetime
import re
from corm.models import *
from urllib.parse import urlparse, parse_qs, urlencode
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse
from django.urls import path
from django.contrib import messages
import requests

AUTHORIZATION_BASE_URL = 'https://login.salesforce.com/services/oauth2/authorize'
TOKEN_URL = 'https://login.salesforce.com/services/oauth2/token'
REFRESH_URL = 'https://login.salesforce.com/services/oauth2/token'

CHANNELS_URL = '/services/data/v50.0/limits/recordCount'
ACCOUNTS_URL = '/services/data/v50.0/sobjects/Account'
CONTACTS_URL = '/services/data/v50.0/sobjects/Contact'

def authenticate(request):
    community = get_object_or_404(Community, id=request.session['community'])
    # if not community.management.can_add_source():
    #     messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
    #     return redirect('sources', community_id=community.id)
    client_id = settings.SALESFORCE_CLIENT_ID
    salesforce_auth_scope = [
        'api',
        'refresh_token',
        'offline_access',
    ]
    callback_uri = request.build_absolute_uri(reverse('salesforce_callback'))
    client = OAuth2Session(client_id, scope=salesforce_auth_scope, redirect_uri=callback_uri)
    authorization_url, state = client.authorization_url(AUTHORIZATION_BASE_URL)

    # State is used to prevent CSRF, keep this for later.
    request.session['oauth_state'] = state
    return redirect(authorization_url)


def callback(request):
    client_id = settings.SALESFORCE_CLIENT_ID
    client_secret = settings.SALESFORCE_CLIENT_SECRET
    callback_uri = request.build_absolute_uri(reverse('salesforce_callback'))
    client = OAuth2Session(client_id, state=request.session['oauth_state'], redirect_uri=callback_uri)
    community = get_object_or_404(Community, id=request.session['community'])

    try:
        token = client.fetch_token(TOKEN_URL, code=request.GET.get('code', None), client_secret=client_secret)
        print("Token: %s" % token)
        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, auth_id=token.get('id'), connector="corm.plugins.salesforce", server=token.get('instance_url'), defaults={"auth_secret": token['access_token'], "auth_refresh": token.get('refresh_token', None)})
        source, created = Source.objects.update_or_create(community=community, auth_id=token.get('id'), connector="corm.plugins.salesforce", server=token.get('instance_url'), defaults={'name':'Salesforce', 'icon_name': 'fab fa-salesforce', 'auth_secret': token['access_token']})
        if created:
            messages.success(request, 'Your Salesforce org has been connected!')
        else:
            messages.info(request, 'Your Salesforce source has been updated.')

        return redirect(reverse('channels', kwargs={'community_id':community.id, 'source_id':source.id}))
    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect your Salesforce org: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('auth', authenticate, name='salesforce_auth'),
    path('callback', callback, name='salesforce_callback'),
]

def refresh_auth(source):
    try:
        user_cred = UserAuthCredentials.objects.get(connector='corm.plugins.salesforce', auth_secret=source.auth_secret, auth_refresh__isnull=False)
    except UserAuthCredentials.DoesNotExist:
        raise RuntimeError("Unable to refresh accesss token: Unknown credentials")
        
    try:
        client_id = settings.SALESFORCE_CLIENT_ID
        client_secret = settings.SALESFORCE_CLIENT_SECRET
        client = OAuth2Session(client_id)

        new_token = client.refresh_token(REFRESH_URL, refresh_token=user_cred.auth_refresh, auth=HTTPBasicAuth(client_id, client_secret))
        user_cred.auth_secret = new_token.get('access_token')
        user_cred.save()
        source.auth_secret = new_token.get('access_token')
        source.save()
    except Exception as e:
        raise RuntimeError("Unable to refresh accesss token: %s" % e)

    return source

class SalesforcePlugin(BasePlugin):

    def get_identity_url(self, contact):
        return contact.source.server  + "/lightning/r/Contact/" + contact.origin_id + "/view"

    def get_icon_name(self):
        return 'fab fa-salesforce'
        
    def get_auth_url(self):
        return reverse('salesforce_auth')

    def get_source_type_name(self):
        return "Salesforce"

    def get_import_command_name(self):
        return "salesforce"

    def get_source_importer(self, source):
        return SalesforceImporter(source)

    def get_channels(self, source):
        source = refresh_auth(source)
        channels = []
        path = source.server + CHANNELS_URL
        resp = requests.get(path, headers={"Authorization": "Bearer %s" % source.auth_secret})
        if resp.status_code == 200:
            data = resp.json()
            for sobj in data.get('sObjects', []):
                if sobj.get('name') in ('Account', 'Contact'):
                    channels.append(
                        {
                            'id': sobj['name'],
                            'name': sobj.get('name', ''),
                            'topic': '',
                            'count':sobj.get('count', 0),
                            'is_private': False,
                            'is_archived': False,
                        }
                    )
        elif resp.status_code == 403:
            raise RuntimeError("Invalid authentication token")
        else:
            raise RuntimeError("%s (%s)" % (resp.reason, resp.status_code))

        return channels

class SalesforceImporter(PluginImporter):

    def __init__(self, source):
        super().__init__(refresh_auth(source))
        self.TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
        self.API_HEADERS =  {
            'Authorization': 'Bearer %s' % source.auth_secret,
        }
        self.tag_matcher = re.compile(r'\<\@([^>]+)\>')

    def strftime(self, tstamp):
        if tstamp.tzinfo is None:
            tstamp = tstamp.replace(tzinfo=pytz.utc)
        tstamp = tstamp.replace(microsecond=0)
        return tstamp.isoformat()

    def api_call(self, path):
        return self.api_request(self.source.server + path, headers=self.API_HEADERS)

    def import_channel(self, channel, from_date, full_import=False):
        self.customer_tag, created = Tag.objects.get_or_create(community=self.community, name="customer", defaults={'color': 'eff240', 'connector': 'corm.plugins.salesforce', 'editable': False})
        self.prospect_tag, created = Tag.objects.get_or_create(community=self.community, name="prospect", defaults={'color': '40f2dd', 'connector': 'corm.plugins.salesforce', 'editable': False})
        self.lead_tag, created = Tag.objects.get_or_create(community=self.community, name="lead", defaults={'color': '40f29c', 'connector': 'corm.plugins.salesforce', 'editable': False})
        if channel.name == 'Account':
            self.import_accounts(channel, from_date, full_import)
        if channel.name == 'Contact':
            self.import_contacts(channel, from_date, full_import)
        return

    def import_accounts(self, channel, from_date, full_import):
        print("Importing Salesforce Accounts")
        end_date = datetime.datetime.utcnow()
        if (end_date - from_date).days > 7:
            from_date = end_date - datetime.timedelta(days=6, hours=23)
        query_range = urlencode({'start':self.strftime(from_date), 'end':self.strftime(end_date)})
        resp = self.api_call(ACCOUNTS_URL + "/updated?" + query_range)
        if resp.status_code == 200:
            data = resp.json()
            #print(data)
            for sobj_id in data.get('ids', []):
                try:
                    salesforce_account = SourceGroup.objects.get(source=self.source, origin_id=sobj_id)
                except SourceGroup.DoesNotExist:
                    # Not a Company we track
                    return
                self.import_account(sobj_id)
        else:
            print("Status code: %s"% resp.status_code)
            print(resp.content)
    
    def import_account(self, account_id):
        print("Importing Salesforce Account: %s" % account_id)
        resp = self.api_call(ACCOUNTS_URL + "/%s/" % account_id)
        if resp.status_code == 200:
            data = resp.json()
            print(data)
            try:
                salesforce_account = SourceGroup.objects.get(source=self.source, origin_id=data.get('Id'))
                salesforce_account.name = data.get('Name')
                salesforce_account.save()
                company = salesforce_account.company
                company.name = data.get('Name')
                company.website = data.get('Website', company.website)
                company.save()
            except Exception as e:
                print(e)
                company = Company.objects.create(community=self.source.community, name=data.get('Name'), website=data.get('Website'))
                salesforce_account = SourceGroup.objects.create(company=company, source=self.source, name=data.get('Name'), origin_id=data.get('Id'))
            if data.get('Type') == 'Customer' and (company.tag == self.prospect_tag or company.tag is None):
                company.set_tag(self.customer_tag)
            elif data.get('Type') == 'Prospect' and (company.tag == self.customer_tag or company.tag is None):
                company.set_tag(self.prospect_tag)
            elif data.get('Type') not in ('Customer', 'Prospect') and company.tag in (self.customer_tag, self.prospect_tag):
                company.set_tag(None)
        return salesforce_account

    def import_contacts(self, channel, from_date, full_import):
        print("Importing Salesforce Contacts")
        end_date = datetime.datetime.utcnow()
        if (end_date - from_date).days > 7:
            from_date = end_date - datetime.timedelta(days=6, hours=23)
        query_range = urlencode({'start':self.strftime(from_date), 'end':self.strftime(end_date)})
        resp = self.api_call(CONTACTS_URL + "/updated?" + query_range)
        if resp.status_code == 200:
            data = resp.json()
            print(data)
            for sobj_id in data.get('ids', []):
                self.import_contact(channel, sobj_id)
        else:
            print("Status code: %s"% resp.status_code)
            print(resp.content)

    def import_contact(self, channel, contact_id):
        resp = self.api_call(CONTACTS_URL + "/%s/" % contact_id)
        if resp.status_code == 200:
            data = resp.json()
            print(data)
            # See if we're already tracking this person
            members = Member.objects.filter(community=self.source.community).filter(Q(email_address=data.get('Email')) | Q(contact__email_address=data.get('Email')) ).distinct()
            if len(members) != 1:
                print("%s Members found matching %s" % (len(members), data.get('Email')))
                return
            member = members[0]
            try:
                salesforce_account = SourceGroup.objects.get(source=self.source, origin_id=data.get('AccountId'))
            except SourceGroup.DoesNotExist:
                salesforce_account = self.import_account(data.get('AccountId'))
            tstamp = self.strptime(data.get('LastModifiedDate')).replace(tzinfo=None)
            full_name = data.get('Name')
            contact, created = Contact.objects.get_or_create(origin_id=data.get('Id'), source=self.source, defaults={'member':member, 'detail':full_name, 'email_address':data.get('Email')})
            if created:
                self.update_identity(contact)
            member.set_company(salesforce_account.company)
            member.save()
