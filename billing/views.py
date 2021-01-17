from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django import forms
from django.db.models import Q

import json
import datetime

import stripe, djstripe
from djstripe import webhooks

from corm.models import Community
from billing.models import Organization, Management
from frontendv2.views import SavannahView, get_session_community
from frontendv2.models import EmailMessage

# Create your views here.
class NewCommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ['name', 'logo']
    
class CommunityCreationEmail(EmailMessage):
    def __init__(self, community):
        super(CommunityCreationEmail, self).__init__(community.owner, community)
        self.subject = "A new community had been created: %s" % self.community.name
        self.category = "community_creation"

        self.text_body = "emails/new_community_created.txt"
        self.html_body = "emails/new_community_created.html"


@login_required
def signup_community(request):
    community = Community(owner=request.user)
    if request.method == "POST":
        form = NewCommunityForm(request.POST, files=request.FILES, instance=community)
        if form.is_valid():
            new_community = form.save()
            new_community.bootstrap()
            msg = CommunityCreationEmail(new_community)
            msg.send(settings.ADMINS)
            # Redirect to company creation form
            #messages.success(request, "Welcome to your new Communtiy! Learn what to do next in our <a target=\"_blank\" href=\"http://docs.savannahhq.com/getting-started/\">Getting Started</a> guide.")
            return redirect('billing:signup_org', community_id=new_community.id)
    else:
        form = NewCommunityForm(instance=community)

    context = {
        "form": form,
    }
    return render(request, 'billing/signup_community.html', context)


@login_required
def signup_org(request, community_id):
    # If community doesn't exist
        # Redirect to community signup form
    try:
         community = Community.objects.get(Q(owner=request.user) | Q(managers__in=request.user.groups.all()), id=community_id)
    except Exception as e:
        messages.error(request, "Unknown Community")
        return redirect('billing:signup')

    stripe.api_key =settings.STRIPE_SECRET_KEY
    # If community has a company
        # Redirect to subscription form
    try:
        management = Management.objects.get(community=community)
        return redirect('billing:signup_subscribe', community_id=community.id)
    except:
        pass

    try:
        customer = stripe.Customer.create(
            email=request.user.email,
            name=community.name,
        )
        djstripe_customer = djstripe.models.Customer.sync_from_stripe_data(customer)
        djstripe_customer.subscriber = community
        djstripe_customer.save()
        org, created = Organization.objects.get_or_create(customer=djstripe_customer, defaults={'name': community.name, 'email': request.user.email})

        management, created = Management.objects.get_or_create(org=org, community=community)
        return redirect('billing:signup_subscribe', community_id=community.id)
    except Exception as e:
        messages.error(request, "Failed to find or create a billing organization for %s" % community.name)
        messages.error(request, e)
        customer = None
        org = None
        return redirect('billing:signup')

@login_required
def signup_subscribe_session(request, community_id):
 
    management = get_object_or_404(Management, community_id=community_id)
    community = management.community
    org = management.org


    if request.method == 'POST':
 
        # Set Stripe API key
        stripe.api_key = settings.STRIPE_SECRET_KEY
 
        # Create Stripe Checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            client_reference_id=community.id,
            allow_promotion_codes=True,
            line_items=[
                {
                    "price": settings.STRIPE_DEFAULT_PLAN,
                    "quantity": 1
                }
            ],
            subscription_data={
                "trial_period_days": 30,
            },
            customer=org.customer.id,
            success_url=settings.SITE_ROOT + reverse('billing:subscription_success', kwargs={'community_id': community.id}) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url= settings.SITE_ROOT + reverse('billing:subscription_cancel', kwargs={'community_id': community.id}), # The cancel_url is typically set to the original product page
        )
 
    return JsonResponse({'sessionId': checkout_session['id']})

@login_required
def signup_subscribe(request, community_id):
    # If community has a subscription
        # Redirect to Stripe customer portal

    management = get_object_or_404(Management, community_id=community_id)
    community = management.community
    org = management.org

    context = {
        "community": community,
        "org": org,
        "STRIPE_KEY": settings.STRIPE_PUBLIC_KEY,
        "STRIPE_PLAN": settings.STRIPE_DEFAULT_PLAN,
    }
    return render(request, 'billing/signup_subscribe.html', context)

@login_required
def create_checkout_session(request, community_id):
    # Create Stripe.checkout.Session
        # Use community_id as client_reference_id
    # Return session id in JSON
    pass

@login_required
def subscription_success(request, community_id):
    # Redirect to Community dashboard
    community = get_object_or_404(Community, id=community_id)
    messages.success(request, "Your subscription to Savannah CRM has begun!")
    return redirect('dashboard', community_id=community.id)

@login_required
def subscription_cancel(request, community_id):
    # Redirect to subscribe_community
    community = get_object_or_404(Community, id=community_id)
    messages.error(request, "Unable to process your subscription")
    return redirect('billing:signup_subscribe', community_id=community.id)

@webhooks.handler("checkout.session.completed")
def checkout_session_completed(event, **kwargs):
    # Get community_id from client_reference_id
    session = event.data["object"]
    community_id = session["client_reference_id"]
    subscription_id = session["subscription"]
    management = Management.objects.get(community_id=community_id)

    # Add subscription to Management model of this community
    management.subscribe(subscription_id)

@webhooks.handler("customer.subscription.deleted")
def subscription_canceled(event, **kwargs):
    # Deactive the community this subscription belonged to
    subscription = event.data["object"]
    Management.unsubscribe(subscription['id'])

class TrialEndingEmail(EmailMessage):
    def __init__(self, community):
        system_user = get_object_or_404(User, username=settings.SYSTEM_USER)
        super(TrialEndingEmail, self).__init__(system_user, community)
        self.subject = "Your trial period for %s is about to end" % self.community.name
        self.category = "trial_ending"

        self.text_body = "emails/trial_ending.txt"
        self.html_body = "emails/trial_ending.html"

@webhooks.handler("customer.subscription.trial_will_end")
def send_trial_end_email(event, **kwargs):
    subscription = event.data["object"]
    mgmt = Management.objects.get(subscription__id=subscription['id'])
    community = mgmt.community
    msg = TrialEndingEmail(community)
    msg.context.update({
        "trial_end": datetime.datetime.fromtimestamp(subscription["trial_end"]),
        "price":   (subscription["plan"]["amount"]/100),
        "currency": subscription["plan"]["currency"],
        "interval": subscription["plan"]["interval"],
    })
    msg.send(community.owner.email)

class PaymentFailedEmail(EmailMessage):
    def __init__(self, community):
        system_user = get_object_or_404(User, username=settings.SYSTEM_USER)
        super(PaymentFailedEmail, self).__init__(system_user, community)
        self.subject = "Problems with your Savannah CRM Account"
        self.category = "billing_error"

        self.text_body = "emails/payment_failed.txt"
        self.html_body = "emails/payment_failed.html"

@webhooks.handler("invoice.payment_failed")
def payment_failed(event, **kwargs):
    invoice = event.data["object"]
    mgmt = Management.objects.get(subscription__id=invoice['subscription'])
    community = mgmt.community
    if invoice["attempt"] >= 3:
        Management.suspend(invoice['subscription'])
    msg = PaymentFailedEmail(community)
    msg.context.update({
        "invoice_date": datetime.datetime.fromtimestamp(invoice["created"]),
        "next_attempt": datetime.datetime.fromtimestamp(invoice["next_payment_attempt"]),
        "price":   (invoice["amount_due"]/100),
        "invoice_url": invoice["hosted_invoice_url"],

    })
    msg.send(community.owner.email)

@login_required
def manage_account(request, community_id):
    community = get_object_or_404(Community, id=community_id)
    if community.owner != request.user:
        messages.warning(request, "Only the owner of this community can access billing information")
        return redirect('dashboard', community_id=community_id)

    try:
        management = Management.objects.get(community_id=community_id)
    except Management.DoesNotExist:
        return redirect('billing:signup_org', community_id=community.id)

    org = management.org

    if management.subscription is None:
        return redirect('billing:signup_subscribe', community_id=community.id)

    # Set Stripe API key
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Create Stripe Billing Portal session
    session = stripe.billing_portal.Session.create(
        customer=org.customer.id,
        return_url=settings.SITE_ROOT + reverse('dashboard', kwargs={'community_id': community.id}),
    )
    if 'url' in session:
        return redirect(session['url'])
    else:
        message.error(request, "Unable to launch Stripe Customer Portal")
        return redirect('dashboard', community_id=community_id)

