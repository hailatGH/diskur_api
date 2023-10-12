''' Django notifications signal file '''
# -*- coding: utf-8 -*-
from django.dispatch import Signal

notify = Signal(  # pylint: disable=invalid-name
    ['recipient', 'actor', 'verb', 'action_object', 'target', 'description',
    'timestamp', 'level', 'send_email', 'send_telegram', 'type', 'category',
    'push_notification_title', 'push_notification_description']
)
