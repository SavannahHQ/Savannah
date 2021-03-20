"""savannah URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings

from .views import signup_community, signup_org, signup_subscribe, signup_subscribe_session, subscription_success, subscription_cancel, manage_account

import djstripe

app_name = 'billing'
urlpatterns = [
    path("stripe/", include("djstripe.urls", namespace="djstripe")),
    path("signup/new/", signup_community, name="signup"),
    path("signup/<int:community_id>/", signup_org, name="signup_org"),
    path("signup/<int:community_id>/subscribe", signup_subscribe, name="signup_subscribe"),
    path("signup/<int:community_id>/upgrade", signup_subscribe, name="upgrade"),
    path("signup/<int:community_id>/session", signup_subscribe_session, name="signup_subscribe_session"),
    path("signup/<int:community_id>/success", subscription_success, name="subscription_success"),
    path("signup/<int:community_id>/cancel", subscription_cancel, name="subscription_cancel"),
    path("manage/<int:community_id>/", manage_account, name="manage_account"),
]
