from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse

import json

import stripe, djstripe
from corm.models import Community
from billing.models import Company, Management
from frontendv2.views import SavannahView

# Create your views here.
@login_required
def create_community(request):
    # If POST
        # Create community
        # Redirect to company creation form
    # If GET
        # Show community creation form
    pass

@login_required
def create_company(request, community_id):
    # If community has a company
        # Redirect to subscription form

    # If POST
        # Create Customer & Company
        # Redirect to subscription form
    # If GET
        # Show company creation form
    pass

@login_required
def subscribe_community(request, community_id):
    # If community has a subscription
        # Redirect to Stripe customer portal

    #If GET
        # Show subscription options form
        # Use Stripe Checkout button
    pass

@login_required
def create_checkout_session(request, community_id):
    # Create Stripe.checkout.Session
        # Use community_id as client_reference_id
    # Return session id in JSON

@login_required
def subscription_success(request):
    # Redirect to Community dashboard
    pass

@login_required
def subscription_cancel(request):
    # Redirect to subscribe_community
    pass

@webhooks.handler("checkout.session.completed")
def checkout_session_completed(event, **kwargs):
    # Get community_id from client_reference_id
    session = event.data["object"]
    community_id = session["client_reference_id"]
    subscription_id = session["subscription"]
    # Add subscription to Management model of this community


# def get_session_company(request):
#     community_id = request.session.get('community')
#     if community_id is not None:
#         try:
#             return Company.objects.get(communities__id=community_id)
#         except:
#             pass
#     return None

# @login_required
# def create_company(request, community_id):
#     community = get_object_or_404(Community, id=community_id)

#     stripe.api_key =settings.STRIPE_TEST_SECRET_KEY
#     try:
#         management = Management.objects.get(community=community)
#         company = management.company
#     except:
#         try:
#             customer = stripe.Customer.create(
#                 email=request.user.email,
#                 name=community.name,
#             )
#             djstripe_customer = djstripe.models.Customer.sync_from_stripe_data(customer)
#             djstripe_customer.subscriber = community
#             djstripe_customer.save()
#             company, created = Company.objects.get_or_create(customer=djstripe_customer, defaults={'name': community.name, 'email': request.user.email})

#             management, created = Management.objects.get_or_create(company=company, community=community)
#         except Exception as e:
#             messages.error(request, "Failed to find or create a Company for %s" % community.name)
#             messages.error(request, e)
#             customer = None
#             company = None
#     return redirect('billing:subscribe', community_id=community.id)

# @login_required
# def subscribe(request, community_id):
#     management = get_object_or_404(Management, community_id=community_id)
#     community = management.community
#     company = management.company

#     if request.method == 'POST':
#         stripe.api_key =settings.STRIPE_TEST_SECRET_KEY
#         data = json.loads(request.body.decode('utf-8'))
#         try:
#             # Attach the payment method to the customer
#             stripe.PaymentMethod.attach(
#                 data['paymentMethodId'],
#                 customer=data['customerId'],
#             )
#             # Set the default payment method on the customer
#             stripe.Customer.modify(
#                 data['customerId'],
#                 invoice_settings={
#                     'default_payment_method': data['paymentMethodId'],
#                 },
#             )

#             # Create the subscription
#             subscription = stripe.Subscription.create(
#                 customer=company.customer.id,
#                 items=[
#                     {
#                     'price': settings.STRIPE_DEFAULT_PLAN,
#                     },
#                 ],
#                 metadata={
#                     'community_id': community.id,
#                     'community_name': community.name
#                 },
#                 expand=['latest_invoice.payment_intent'],
#                 )
#             djstripe_subscription = djstripe.models.Subscription.sync_from_stripe_data(subscription)
#             management.subscription = djstripe_subscription
#             management.save()
#             messages.success(request, "Subscription added!")
#             return JsonResponse(subscription)
#         except Exception as e:
#             return JsonResponse({'error':{'message': str(e)}})
    
#     context = {
#         "community": community,
#         "company": company,
#         "STRIPE_KEY": settings.STRIPE_TEST_PUBLIC_KEY,
#         "STRIPE_PLAN": 'price_1HLxhJLZDN7eRvmoW5g5PGVj'
#     }
#     return render(request, 'billing/subscribe.html', context)
