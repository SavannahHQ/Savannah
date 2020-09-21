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
import notifications.urls

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/v1/', include('apiv1.urls')),
    path('', include('frontendv2.urls')),
    path('slack/', include('corm.plugins.slack')),
    path('github/', include('corm.plugins.github')),
    path('gitlab/', include('corm.plugins.gitlab')),
    path('discourse/', include('corm.plugins.discourse')),
    path('discord/', include('corm.plugins.discord')),
    path('rss/', include('corm.plugins.rss')),
    path('inbox/notifications/', include(notifications.urls, namespace='notifications')),
] 
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except:
        # django-debug-toolbar is not installed
        pass