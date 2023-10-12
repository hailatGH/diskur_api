from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver

from moogts.enums import MoogtWebsocketMessageType
from .models import ArgumentActivity, Argument
from .utils import notify_ws_clients_for_argument as notify_ws_clients_for_argument


@receiver(post_save, sender=ArgumentActivity)
def activity_created_notification(sender, instance, created, **kwargs):
    argument = instance.argument
    type = MoogtWebsocketMessageType.ARGUMENT_UPDATED.value

    if argument.moogt and created:
        async_to_sync(notify_ws_clients_for_argument)(argument, message_type=type)
