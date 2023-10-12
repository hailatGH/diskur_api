"""moogtmeda URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
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
from django.views.generic import TemplateView
from django.urls import re_path, include, path
from django.conf.urls.static import static
from django.conf import settings

from meda import views as meda_views


urlpatterns = [
    # re_path(r'^$', TemplateView.as_view(template_name='meda/index.html'), name='index'),
    re_path(r'^legacy$', meda_views.index, name='legacy_index'),
    re_path(r'^accounts/', include('allauth.urls')),

    # this url is used to generate email content
    re_path(r'^password-reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
            TemplateView.as_view(template_name="password_reset_confirm.html"),
            name='password_reset_confirm'),

    re_path(r'^management/', admin.site.urls),
    re_path(r'^avatar/', include('avatar.urls')),
    re_path(r'^users/', include('users.urls')),
    re_path(r'^notifications/',
            include('notifications.urls', namespace='notifications')),
    re_path(r'^comments/', include('django_comments_xtd.urls')),
    re_path(r'^preferences/', include('dynamic_preferences.urls')),
    re_path(r'^api/', include('api.urls')),
    re_path(r'^api-auth/', include('rest_framework.urls')),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += [re_path(r'^__debug__/', include(debug_toolbar.urls))]
