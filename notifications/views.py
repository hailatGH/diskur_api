# -*- coding: utf-8 -*-
''' Django Notifications exemple views '''
import json
from distutils.version import StrictVersion  # pylint: disable=no-name-in-module,import-error

from django import get_version
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.forms import model_to_dict
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.generic import ListView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from chat.utils import unread_messages
from moogts.models import Moogt

from notifications import settings
from notifications.models import Notification
from notifications.settings import get_config
from notifications.utils import id2slug, slug2id, notification_model_to_dict

if StrictVersion(get_version()) >= StrictVersion('1.7.0'):
    from django.http import JsonResponse  # noqa
else:
    # Django 1.6 doesn't have a proper JsonResponse
    import json
    from django.http import HttpResponse  # noqa

    def date_handler(obj):
        return obj.isoformat() if hasattr(obj, 'isoformat') else obj

    def JsonResponse(data):  # noqa
        return HttpResponse(
            json.dumps(data, default=date_handler),
            content_type="application/json")


class NotificationViewList(ListView):
    template_name = 'notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = settings.get_config()['PAGINATE_BY']

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(NotificationViewList, self).dispatch(
            request, *args, **kwargs)


class AllNotificationsList(NotificationViewList):
    """
    Index page for authenticated user
    """

    def get_queryset(self):
        if settings.get_config()['SOFT_DELETE']:
            qset = self.request.user.notifications.active()
        else:
            qset = self.request.user.notifications.all()
        return qset


class UnreadNotificationsList(NotificationViewList):

    def get_queryset(self):
        queryset = self.request.user.notifications.unread_notifications()
        if json.loads(self.request.GET.get('related_to_me', 'false')):
            queryset = queryset.sort_related_notifications_first(
                self.request.user)

        return queryset


@login_required
@csrf_protect
def mark_all_as_read(request):
    request.user.notifications.mark_all_as_read()

    _next = request.GET.get('next')

    if _next:
        return redirect(_next)
    return redirect('notifications:unread')


@api_view(http_method_names=['GET'])
@login_required
def mark_as_read(request, slug=None):
    notification_id = slug2id(slug)

    notification = get_object_or_404(
        Notification, recipient=request.user, id=notification_id)
    notification.mark_as_read()

    _next = request.GET.get('next')

    if _next:
        return redirect(_next)

    return redirect('notifications:unread')


@login_required
def mark_as_unread(request, slug=None):
    notification_id = slug2id(slug)

    notification = get_object_or_404(
        Notification, recipient=request.user, id=notification_id)
    notification.mark_as_unread()

    _next = request.GET.get('next')

    if _next:
        return redirect(_next)

    return redirect('notifications:unread')


@login_required
def delete(request, slug=None):
    notification_id = slug2id(slug)

    notification = get_object_or_404(
        Notification, recipient=request.user, id=notification_id)

    if settings.get_config()['SOFT_DELETE']:
        notification.deleted = True
        notification.save()
    else:
        notification.delete()

    _next = request.GET.get('next')

    if _next:
        return redirect(_next)

    return redirect('notifications:all')


@api_view(http_method_names=['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def live_unread_notification_count(request):
    try:
        user_is_authenticated = request.user.is_authenticated()
    except TypeError:  # Django >= 1.11
        user_is_authenticated = request.user.is_authenticated

    if not user_is_authenticated:
        data = {
            'unread_following_moogt_cards': 0,
            'unread_user_moogt_cards': 0,
            'unread_notifications_count': 0,
            'unread_message_notifications_count': 0
        }
    else:

        following_unread_cards_count = 0
        user_moogts_unread_card_count = 0

        # for i in request.user.following_moogts.all():
        #     unread_cards = i.unread_cards_count(request.user)
        #     if(unread_cards):
        #         if(i.proposition == request.user or i.opposition == request.user):
        #             user_moogts_unread_card_count += unread_cards
        #         else:
        #             following_unread_cards_count += unread_cards

        data = {
            'unread_following_moogt_cards': following_unread_cards_count,
            'unread_user_moogt_cards': user_moogts_unread_card_count,
            'unread_notifications_count': request.user.notifications.unread_count(
                Notification.NOTIFICATION_CATEGORY.normal
            ),
            'unread_message_notifications_count': unread_messages(request.user)

        }
    return JsonResponse(data)


@api_view(http_method_names=['GET'])
def live_unread_notification_list(request):
    ''' Return a json with a unread notification list '''
    try:
        user_is_authenticated = request.user.is_authenticated()
    except TypeError:  # Django >= 1.11
        user_is_authenticated = request.user.is_authenticated

    if not user_is_authenticated:
        data = {
            'unread_count': 0,
            'unread_list': [],
            'has_unread_messages': False
        }
        return JsonResponse(data)

    default_num_to_fetch = get_config()['NUM_TO_FETCH']
    try:
        # If they don't specify, make it 5.
        num_to_fetch = request.GET.get('max', default_num_to_fetch)
        num_to_fetch = int(num_to_fetch)
        if not (1 <= num_to_fetch <= 100):
            num_to_fetch = default_num_to_fetch
    except ValueError:  # If casting to an int fails.
        num_to_fetch = default_num_to_fetch

    format_html = False
    if 'format' in request.GET:
        format_html = request.GET['format'] == 'html'

    unread_list = []

    notification_type = request.query_params.get('type', 'normal')

    parent = request.query_params.get('parent_id', None)
    if parent:
        parent = get_object_or_404(Notification, pk=parent)

    if notification_type == 'message':
        category = Notification.NOTIFICATION_CATEGORY.message
        queryset = request.user.notifications.unread_messages(
            parent_notification=parent)
    else:
        category = Notification.NOTIFICATION_CATEGORY.normal
        queryset = request.user.notifications.unread_notifications(
            parent_notification=parent)

    if json.loads(request.GET.get('related_to_me', 'false')):
        queryset = queryset.annotate_related_notifications(request.user)
        queryset = queryset.sort_related_notifications_first()

    for notification in queryset[0:num_to_fetch]:
        if format_html:
            notification_html = render_to_string(
                'notifications/_notification.html', {'notification': notification})
            unread_list.append(notification_html)
        else:
            struct = notification_model_to_dict(notification)
            unread_list.append(struct)

        if request.GET.get('mark_as_read'):
            notification.mark_as_read()
    data = {
        'unread_count': request.user.notifications.unread_count(category),
        'unread_list': unread_list,
    }
    return JsonResponse(data)


@api_view(http_method_names=['GET'])
def live_all_notification_list(request):
    ''' Return a json with a unread notification list '''
    try:
        user_is_authenticated = request.user.is_authenticated()
    except TypeError:  # Django >= 1.11
        user_is_authenticated = request.user.is_authenticated

    if not user_is_authenticated:
        data = {
            'all_count': 0,
            'all_list': []
        }
        return JsonResponse(data)

    default_num_to_fetch = get_config()['NUM_TO_FETCH']
    default_page = 1
    try:
        # If they don't specify, make it 5.
        num_to_fetch = request.GET.get('max', default_num_to_fetch)
        num_to_fetch = int(num_to_fetch)
        page = request.GET.get('page', default_page)
        page = int(page)
        if not (1 <= num_to_fetch <= 100):
            num_to_fetch = default_num_to_fetch
        if page < 1:
            page = default_page
    except ValueError:  # If casting to an int fails.
        num_to_fetch = default_num_to_fetch
        page = default_page

    all_list = []

    query_set = request.user.notifications.all_normal_notifications().all()

    paginator = Paginator(query_set, num_to_fetch)
    current_page = paginator.page(page)

    for notification in current_page.object_list:
        struct = notification_model_to_dict(notification)
        all_list.append(struct)
        if request.GET.get('mark_as_read'):
            notification.mark_as_read()
    data = {
        'all_count': request.user.notifications.all_normal_notifications().count(),
        'all_list': all_list,
        'has_next': current_page.has_next(),
        'has_prev': current_page.has_previous()
    }
    return JsonResponse(data)


def live_all_notification_count(request):
    try:
        user_is_authenticated = request.user.is_authenticated()
    except TypeError:  # Django >= 1.11
        user_is_authenticated = request.user.is_authenticated

    if not user_is_authenticated:
        data = {
            'all_count': 0
        }
    else:
        data = {
            'all_count': request.user.notifications.all_normal_notifications().count(),
        }
    return JsonResponse(data)


@api_view(http_method_names=['GET'])
def live_mark_all_as_read(request):
    """Mark all notifications as read"""
    if not request.user.is_authenticated:
        return JsonResponse({'message': 'You must be authenticated first.'}, status=401)

    parent = request.query_params.get('parent_id', None)
    if parent:
        parent = get_object_or_404(Notification, pk=parent)
        Notification.objects.mark_all_in_group_as_read(parent)
        return JsonResponse({'message': 'Success!'})

    request.user.notifications.mark_all_as_read()
    return JsonResponse({'message': 'Success!'})


@api_view(http_method_names=['GET'])
def live_mark_as_read(request, pk=None):
    """Mark all notifications as read"""
    notification = get_object_or_404(
        request.user.notifications.unread(), pk=pk)
    notification.mark_as_read()
    return JsonResponse({'message': 'Success!'})


@api_view(http_method_names=['GET'])
def live_mark_messages_as_read(request, slug=None):
    """Mark message notifications as read"""
    if not request.user.is_authenticated:
        return JsonResponse({'message': 'You must be authenticated first.'}, status=401)

    request.user.notifications.mark_messages_as_read()
    return JsonResponse({'message': 'Success!'})
