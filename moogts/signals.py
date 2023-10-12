from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver

from .enums import MoogtWebsocketMessageType
from .models import MoogtActivity
from .utils import notify_ws_clients


@receiver(post_save, sender=MoogtActivity)
def activity_created_notification(sender, instance, created, **kwargs):
    type = MoogtWebsocketMessageType.MOOGT_UPDATED.value
    async_to_sync(notify_ws_clients)(instance.moogt, message_type=type)
