'''' Django notifications utils file '''
# -*- coding: utf-8 -*-
import logging
import json
import sys

from django.forms.models import model_to_dict
from google.auth.exceptions import DefaultCredentialsError
from firebase_admin.messaging import Message, Notification
from fcm_django.models import FCMDevice


if sys.version > '3':
    long = int  # pylint: disable=invalid-name


logger = logging.getLogger(__name__)


def slug2id(slug):
    return long(slug) - 110909


def id2slug(notification_id):
    return notification_id + 110909


def notification_model_to_dict(notification: Notification):
    from users.serializers import MoogtMedaUserSerializer
    
    struct = model_to_dict(notification)
    struct['slug'] = id2slug(notification.id)

    if notification.actor:
        struct['actor'] = MoogtMedaUserSerializer(notification.actor).data
    if notification.target:
        struct['target'] = str(notification.target)
    if notification.action_object:
        struct['action_object'] = str(notification.action_object)
    if notification.data:
        struct['data'] = notification.data
    if hasattr(notification, 'child_notifications_count'):
        struct['child_notifications_count'] = notification.child_notifications_count
    if hasattr(notification, 'related_to_me'):
        struct['related_to_me'] = notification.related_to_me == 1

    return struct


def send_fcm_notification(notification, recipient_ids, title, description):
    try:
        fcm_devices = FCMDevice.objects.filter(user_id__in=recipient_ids)

        message = Message(
            data={
                'title': title,
                'body': description,
                'payload': json.dumps(notification_model_to_dict(notification), default=str)
            },
        )
        fcm_devices.send_message(message)
        logger.info(f'Sent an FCM notification!')
    except DefaultCredentialsError as err:
        logger.error(f'Error while sending FCM notification: {err}')
