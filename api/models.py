from django.contrib.contenttypes.fields import (GenericForeignKey)
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .enums import ShareProvider


class Tag(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name


class ShareStats(models.Model):
    # The social media we are sharing to.
    provider = models.CharField(max_length=25,
                                choices=[(type.name, type.value) for type in ShareProvider])

    # The number of share on this particular platform.
    share_count = models.PositiveIntegerField(default=0)

    # The following fields are for the GenericForeignKey
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()


class TelegramChatToUser(models.Model):
    from users.models import MoogtMedaUser
    chat_id = models.CharField(max_length=128, unique=True)
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='telegram_chat',
                             null=True,
                             on_delete=models.SET_NULL)
    enable_notifications = models.BooleanField(default=True)

    class Meta:
        unique_together = ('chat_id', 'user')
