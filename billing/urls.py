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

import djstripe
from billing.views import create_company, subscribe

app_name = 'billing'
urlpatterns = [
    path("stripe/", include("djstripe.urls", namespace="djstripe")),
    path("create_company/<int:community_id>/", create_company, name="create_company"),
    path("subscribe/<int:community_id>/", subscribe, name="subscribe"),
]
