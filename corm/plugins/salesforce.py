from corm.plugins import BasePlugin, PluginImporter
import datetime
import re
import pytz
import uuid
from corm.models import *
from urllib.parse import urlparse, parse_qs, urlencode
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, reverse, render
from django.contrib.auth.decorators import login_required
from django.urls import path
from django.contrib import messages
import requests

from rest_framework import serializers, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound
from apiv1.serializers import TagsField
from frontendv2.views import SavannahView

AUTHORIZATION_BASE_URL = 'https://login.salesforce.com/services/oauth2/authorize'
DEFAULT_LOGIN_URL = 'https://login.salesforce.com/'

QUERY_URL = '/services/data/v51.0/query/'
CHANNELS_URL = '/services/data/v51.0/limits/recordCount'
ACCOUNTS_URL = '/services/data/v51.0/sobjects/Account'
CONTACTS_URL = '/services/data/v51.0/sobjects/Contact'
CREDENTIALS_URL = '/services/data/v52.0/tooling/sobjects/NamedCredential'

class SalesforceAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Authorization"

    def authenticate(self, request):
        try:
            token = request.GET['auth_token']
        except KeyError:
            auth = request.META.get('HTTP_AUTHORIZATION', '').split(" ")
            if not auth or auth[0].lower() != 'token':
                return None

            if len(auth) == 1:
                msg = 'Invalid token header. No credentials provided.'
                raise AuthenticationFailed(msg)
            elif len(auth) > 2:
                msg = 'Invalid token header. Token string should not contain spaces.'
                raise AuthenticationFailed(msg)

            try:
                token = str(auth[1])
            except UnicodeError:
                msg = 'Invalid token header. Token string should not contain invalid characters.'
                raise AuthenticationFailed(msg)

        source = None
        try:
            source = Source.objects.get(connector="corm.plugins.salesforce", api_key=token, enabled=True)
        except Source.DoesNotExist:
            msg = 'Invalid token. Token is not associated with any API Integration'
            raise AuthenticationFailed(msg)

        request.source = source
        return (source.community.owner, token)

class SavannahIntegrationView(APIView):
    authentication_classes = [SalesforceAuthentication]
    permission_classes = [permissions.IsAuthenticated]

class MemberDetail(SavannahIntegrationView):
    """
    Retrieve a Member identity instance.
    """
    def get(self, request, format=None):
        origin_id = request.GET.get('origin_id')
        origin_email = request.GET.get('origin_email')
        if origin_id is None:
            raise APIException(detail='origin_id is required')
        if origin_email is None:
            raise APIException(detail='origin_email is required')
        # See if the SFDC ID matches an identity in this souce
        try:
            identity = Contact.objects.get(source=request.source, origin_id=origin_id)
        except:
            # no matching origin_id
            # Try matching by email address in this source
            try:
                identity = Contact.objects.get(source=request.source, email_address=origin_email)
            except:
                # Try matching by email address anywhere in this community
                try:
                    members = Member.objects.filter(community=request.source.community).filter(Q(email_address=origin_email) | Q(contact__email_address=origin_email))
                    member = members.distinct().get()
                    identity, created = member.contact_set.get_or_create(source=request.source, origin_id=origin_id, defaults={'email_address': origin_email, 'detail':origin_email})
                except Member.DoesNotExist:
                    raise NotFound(detail="No Member matching ID or Email")
                except Member.MultipleObjectsReturned:
                    raise NotFound(detail='More than one matching Member exists')
                        
        serializer = SalesforceMemberSerializer(identity)
        return Response(serializer.data)

class SalesforceMemberSerializer(serializers.Serializer):
    member_id = serializers.IntegerField(source='id')
    origin_id = serializers.CharField(max_length=256)
    email = serializers.EmailField(source='email_address', required=False, allow_null=True)
    name = serializers.CharField(source='member.name', max_length=256, required=False, allow_null=True)
    company = serializers.CharField(source='member.company', required=False)
    first_seen = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    identities = serializers.SerializerMethodField(source='*')
    engagement_levels = serializers.SerializerMethodField(source='*')
    notes = serializers.SerializerMethodField(source='*')
    top_connections = serializers.SerializerMethodField(source='*')
    recent_connections = serializers.SerializerMethodField(source='*')

    def get_first_seen(self, identity):
        return identity.member.first_seen.replace(tzinfo=pytz.UTC).isoformat(timespec='seconds')

    def get_last_seen(self, identity):
        if identity.member.last_seen:
            return identity.member.last_seen.replace(tzinfo=pytz.UTC).isoformat(timespec='seconds')
        else:
            return self.get_first_seen()

    def get_tags(self, identity):
        return list({'name':tag.name, 'color':tag.color} for tag in identity.member.tags.all())

    def get_identities(self, identity):
        return list({'source':identity.source.connector_name, 'detail':identity.detail, 'url':identity.link_url} for identity in Contact.objects.filter(member=identity.member))

    def get_engagement_levels(self, identity):
        return list({'project':level.project.name, 'level':level.level_name} for level in MemberLevel.objects.filter(member=identity.member).order_by('-project__default_project', '-level', 'timestamp'))

    def get_notes(self, identity):
        return list({'tstamp':note.timestamp.replace(tzinfo=pytz.UTC).isoformat(timespec='seconds'), 'author': note.author.username, 'content': note.content} for note in Note.objects.filter(member=identity.member).order_by('-timestamp'))

    def get_top_connections(self, identity):
        return list({'name':c.to_member.name, 'connections':c.connection_count} for c in MemberConnection.objects.filter(from_member=identity.member).order_by('-connection_count')[:5])

    def get_recent_connections(self, identity):
        return list({'name':c.to_member.name, 'tstamp':c.last_connected.replace(tzinfo=pytz.UTC).isoformat(timespec='seconds')} for c in MemberConnection.objects.filter(from_member=identity.member).order_by('-last_connected')[:5])

@login_required
def not_available_view(request):
    context = {
        'feature_name': 'Salesforce Integration',
        'feature_msg': 'Salesforce integration will allow you to connect your Salesforce and Savannah data.',
        'feature_signup': settings.SAVANAH_NEWSLETTER,
        'back_url': reverse('sources', kwargs={'community_id': request.session['community']})
    }
    return render(request, 'savannahv2/feature_not_available.html', context=context)

class SalesforceSetup(SavannahView):
    def _add_sources_message(self):
        pass

    @login_required
    def as_view(request):
        view = SalesforceSetup(request, community_id=request.session['community'])
        if not view.community.management.can_add_source():
            messages.warning(request, "You have reach your maximum number of Sources. Upgrade your plan to add more.")
            return redirect('sources', community_id=view.community.id)

        print(view.community.management.metadata)
        if not view.community.management.can_add_sales_source():
            messages.warning(request, "Your plan does not allow sales integrations. <a class=\"btn btn-sm btn-success\" href=\"%s\">Upgrade your plan</a> to add this source." % reverse('billing:upgrade', kwargs={"community_id":view.community.id}))
            return redirect('sources', community_id=view.community.id)
        context = view.context
        context.update({
            'package_url': settings.SALESFORCE_PACKAGE_URL
        })
        return render(request, 'savannahv2/plugins/salesforce/setup.html', context=context)


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
    login_url = request.headers.get('Referer', DEFAULT_LOGIN_URL)
    token_url = login_url + 'services/oauth2/token'
    try:
        token = client.fetch_token(token_url, code=request.GET.get('code', None), client_secret=client_secret)
        #print("Token: %s" % token)
        new_api_key = uuid.uuid4()
        # query_path = token.get('instance_url') + QUERY_URL + '?q=SELECT+ID,DeveloperName,NamespacePrefix+FROM+NamedCredential'
        # print(query_path)
        # print("Authorization: Bearer %s" % token.get('access_token'))
        # resp = requests.get(query_path, headers={"Authorization": "Bearer %s" % token.get('access_token')})
        # if resp.status_code == 200:
        #     data = resp.json()
        #     print(data)
        #     for record in data['records']:
        #         if record['DeveloperName'] == 'Savannah_CRM_API':
        #             print("ID: %s" % record['Id'])
        #             credential_path = token.get('instance_url') + CREDENTIALS_URL + '/' + record['Id']
        #             print(credential_path)
        #             payload = {
        #                 'Metadata': {
        #                     'principalType': 'Anonymous',
        #                     'label': 'Savannah CRM API',
        #                     'protocol': 'Password',
        #                     'allowMergeFieldsInHeader': True,
        #                     'username': request.user.username,
        #                     'password': str(new_api_key)
        #                 }
        #             }
        #             resp = requests.patch(credential_path, json=payload, headers={"Authorization": "Bearer %s" % token.get('access_token'), 'Content-Type': 'application/json'})
        #             if resp.status_code == 200:
        #                 data = resp.json()
        #                 print(data)
        #             else:
        #                 messages.error(request, "Could not add API key to Salesforce Named Credential: %s" % resp.content)
        #                 return redirect(reverse('sources', kwargs={'community_id':community.id}))
        #         else:
        #             messages.error(request, "Could not find Salesforce Named Credential: Savannah_CRM_API")
        #             return redirect(reverse('sources', kwargs={'community_id':community.id}))
        # else:
        #     messages.error(request, "Error checking Salesforce Named Credentials")
        #     return redirect(reverse('sources', kwargs={'community_id':community.id}))

        cred, created = UserAuthCredentials.objects.update_or_create(user=request.user, auth_id=token.get('id'), connector="corm.plugins.salesforce", server=token.get('instance_url'), defaults={"auth_secret": token['access_token'], "auth_refresh": token.get('refresh_token', None)})
        source, created = Source.objects.update_or_create(community=community, auth_id=token.get('id'), connector="corm.plugins.salesforce", server=token.get('instance_url'), defaults={'name':'Salesforce', 'icon_name': 'fab fa-salesforce', 'auth_secret': token['access_token']})
        if created:
            source.api_key = new_api_key
            source.save()

            messages.success(request, 'Your Salesforce org has been connected!')
            messages.info(request, "Use the provided API Token for your NamedCredential password.")
        else:
            messages.info(request, 'Your Salesforce source has been updated.')

        return redirect(reverse('channels', kwargs={'community_id':community.id, 'source_id':source.id}))
    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Unable to connect your Salesforce org: %s' % e)
        return redirect(reverse('sources', kwargs={'community_id':community.id}))

urlpatterns = [
    path('setup', SalesforceSetup.as_view, name='salesforce_setup'),
    path('auth', authenticate, name='salesforce_auth'),
    path('callback', callback, name='salesforce_callback'),
    path('api/member', MemberDetail.as_view(), name='salesforce_api_member'),
]

def refresh_auth(source):
    try:
        user_cred = UserAuthCredentials.objects.get(connector='corm.plugins.salesforce', auth_secret=source.auth_secret, auth_refresh__isnull=False)
    except UserAuthCredentials.DoesNotExist:
        import pdb; pdb.set_trace()
        raise RuntimeError("Unable to refresh accesss token: Unknown credentials")
        
    try:
        client_id = settings.SALESFORCE_CLIENT_ID
        client_secret = settings.SALESFORCE_CLIENT_SECRET
        client = OAuth2Session(client_id)

        new_token = client.refresh_token(source.server+'/services/oauth2/token', refresh_token=user_cred.auth_refresh, client_id=client_id,  client_secret=client_secret)
        user_cred.auth_secret = new_token.get('access_token')
        user_cred.save()
        source.auth_secret = new_token.get('access_token')
        source.save()
    except Exception as e:
        raise RuntimeError("Failed to refresh accesss token: %s" % e)

    return source

class SalesforcePlugin(BasePlugin):

    def get_add_view(self):
        return SalesforceSetup.as_view
        
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
        channels = [{
            'id': 'Account',
            'name': 'Account',
            'topic': 'Link Salesforce Account records to Savannah Company records',
            'count':1,
            'is_private': False,
            'is_archived': False,
        },
        {
            'id': 'Contact',
            'name': 'Contact',
            'topic': 'Link Salesforce Contact records to Savannah Member records',
            'count':0,
            'is_private': False,
            'is_archived': False,
        }]
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
        print("Importing channel: %s" % channel.name)
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

