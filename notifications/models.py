''' Django notifications models file '''
# -*- coding: utf-8 -*-
# pylint: disable=too-many-lines
from copy import deepcopy
from distutils.version import StrictVersion  # pylint: disable=no-name-in-module,import-error

from django import get_version
from django.conf import settings
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import models
from django.db.models import Count, Q, Case, When, IntegerField
from django.db.models.query import QuerySet
from django.utils import timezone, dateformat
from six import text_type
from jsonfield.fields import JSONField
from model_utils import Choices

from moogter_bot.bot import bot
from notifications import settings as notifications_settings
from notifications.enums import NOTIFICATION_TYPES
from notifications.signals import notify
from notifications.utils import id2slug, send_fcm_notification

if StrictVersion(get_version()) >= StrictVersion('1.8.0'):
    from django.contrib.contenttypes.fields import GenericForeignKey  # noqa
else:
    from django.contrib.contenttypes.generic import GenericForeignKey  # noqa

EXTRA_DATA = notifications_settings.get_config()['USE_JSONFIELD']


def is_soft_delete():
    return notifications_settings.get_config()['SOFT_DELETE']


def assert_soft_delete():
    if not is_soft_delete():
        msg = """To use 'deleted' field, please set 'SOFT_DELETE'=True in settings.
        Otherwise NotificationQuerySet.unread and NotificationQuerySet.read do NOT filter by 'deleted' field.
        """
        raise ImproperlyConfigured(msg)


class NotificationQuerySet(models.query.QuerySet):
    ''' Notification QuerySet '''

    def unsent(self):
        return self.filter(emailed=False)

    def sent(self):
        return self.filter(emailed=True)

    def unread(self, include_deleted=False):
        """Return only unread items in the current queryset"""
        if is_soft_delete() and not include_deleted:
            return self.filter(unread=True, deleted=False)

        # When SOFT_DELETE=False, developers are supposed NOT to touch 'deleted' field.
        # In this case, to improve query performance, don't filter by 'deleted' field
        return self.annotate(
            child_notifications_count=Count('child_notifications')
        ).filter(unread=True)

    def unread_messages(self, include_deleted=False, parent_notification=None):
        qset = self.unread(include_deleted)

        filtering_dict = {
            'category': Notification.NOTIFICATION_CATEGORY.message}

        if parent_notification:
            filtering_dict['parent_notification'] = parent_notification
        else:
            filtering_dict['parent_notification__isnull'] = True
        return qset.filter(**filtering_dict)

    def unread_notifications(self, include_deleted=False, parent_notification=None):
        qset = self.unread(include_deleted)

        filtering_dict = {
            'category': Notification.NOTIFICATION_CATEGORY.normal}

        if parent_notification:
            filtering_dict['parent_notification'] = parent_notification
        else:
            filtering_dict['parent_notification__isnull'] = True
        return qset.filter(**filtering_dict)

    def unread_count(self, category, include_deleted=False):
        if category is None:
            category = Notification.NOTIFICATION_CATEGORY.normal
        qset = self.unread(include_deleted).filter(
            child_notifications_count=0, category=category)

        return qset.count()

    def all_normal_notifications(self, include_deleted=False):
        return self.annotate(
            child_notifications_count=Count('child_notifications')
        ).filter(child_notifications_count=0,
                 category=Notification.NOTIFICATION_CATEGORY.normal)

    def read(self, include_deleted=False):
        """Return only read items in the current queryset"""
        if is_soft_delete() and not include_deleted:
            return self.filter(unread=False, deleted=False)

        # When SOFT_DELETE=False, developers are supposed NOT to touch 'deleted' field.
        # In this case, to improve query performance, don't filter by 'deleted' field
        return self.filter(unread=False)

    def mark_all_in_group_as_read(self, parent):
        if parent:
            parent.unread = False
            parent.save()
            return parent.child_notifications.update(unread=False)

    def mark_all_as_read(self, recipient=None):
        """Mark as read non conversation unread messages in the current queryset.

        Optionally, filter these by recipient first.
        """
        # We want to filter out read ones, as later we will store
        # the time they were marked as read.
        qset = self.unread(True).filter(
            category=Notification.NOTIFICATION_CATEGORY.normal)
        if recipient:
            qset = qset.filter(recipient=recipient)

        return qset.update(unread=False)

    def mark_messages_as_read(self, recipient=None):
        """Mark as read conversation unread messages in the current queryset.

        Optionally, filter these by recipient first
        """
        qset = self.unread(True).filter(
            category=Notification.NOTIFICATION_CATEGORY.message)
        if recipient:
            qset = qset.filter(recipient=recipient)

        return qset.update(unread=False)

    def mark_all_as_unread(self, recipient=None):
        """Mark as unread any read messages in the current queryset.

        Optionally, filter these by recipient first.
        """
        qset = self.read(True)

        if recipient:
            qset = qset.filter(recipient=recipient)

        return qset.update(unread=True)

    def deleted(self):
        """Return only deleted items in the current queryset"""
        assert_soft_delete()
        return self.filter(deleted=True)

    def active(self):
        """Return only active(un-deleted) items in the current queryset"""
        assert_soft_delete()
        return self.filter(deleted=False)

    def mark_all_as_deleted(self, recipient=None):
        """Mark current queryset as deleted.
        Optionally, filter by recipient first.
        """
        assert_soft_delete()
        qset = self.active()
        if recipient:
            qset = qset.filter(recipient=recipient)

        return qset.update(deleted=True)

    def mark_all_as_active(self, recipient=None):
        """Mark current queryset as active(un-deleted).
        Optionally, filter by recipient first.
        """
        assert_soft_delete()
        qset = self.deleted()
        if recipient:
            qset = qset.filter(recipient=recipient)

        return qset.update(deleted=False)

    def mark_as_unsent(self, recipient=None):
        qset = self.sent()
        if recipient:
            qset = qset.filter(recipient=recipient)
        return qset.update(emailed=False)

    def mark_as_sent(self, recipient=None):
        qset = self.unsent()
        if recipient:
            qset = qset.filter(recipient=recipient)
        return qset.update(emailed=True)

    def remove_notification(self, target, sender, notification_type):
        target_ctype = ContentType.objects.get_for_model(target)
        actor_ctype = ContentType.objects.get_for_model(sender)

        self.filter(
            target_content_type=target_ctype,
            target_object_id=target.id,
            actor_content_type=actor_ctype,
            actor_object_id=sender.id,
            type=notification_type
        ).delete()

    def find_related_notifications(self, category, target, recipient=None):
        if target and category:
            content_type = get_content_type_for_model(target)
            return self.unread().filter(recipient=recipient,
                                        category=category,
                                        target_content_type=content_type,
                                        target_object_id=target.pk,
                                        child_notifications_count=0).first()

    def annotate_related_notifications(self, user):
        queryset = self.annotate(
            related_to_me=Case(
                When(target_moogt__opposition=user, then=1),
                When(target_moogt__proposition=user, then=1),
                When(target_argument__user=user, then=1),
                When(target_poll__user=user, then=1),
                When(target_view__user=user, then=1),
                default=0,
                output_field=IntegerField()))

        return queryset

    def sort_related_notifications_first(self):
        return self.order_by('-related_to_me', '-timestamp')

    def mark_notifications_as_read(self, ctype, object_id, timestamp):
        return self.filter(
            action_object_content_type=ctype, action_object_object_id=object_id, timestamp__lte=timestamp).update(unread=False)

class NotificationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().prefetch_related('actor', 'actor__profile')

class Notification(models.Model):
    """
    Action model describing the actor acting out a verb (on an optional
    target).
    Nomenclature based on http://activitystrea.ms/specs/atom/1.0/

    Generalized Format::

        <actor> <verb> <time>
        <actor> <verb> <target> <time>
        <actor> <verb> <action_object> <target> <time>

    Examples::

        <justquick> <reached level 60> <1 minute ago>
        <brosner> <commented on> <pinax/pinax> <2 hours ago>
        <washingtontimes> <started follow> <justquick> <8 minutes ago>
        <mitsuhiko> <closed> <issue 70> on <mitsuhiko/flask> <about 2 hours ago>

    Unicode Representation::

        justquick reached level 60 1 minute ago
        mitsuhiko closed issue 70 on mitsuhiko/flask 3 hours ago

    HTML Representation::

        <a href="http://oebfare.com/">brosner</a> commented on <a href="http://github.com/pinax/pinax">pinax/pinax</a> 2 hours ago # noqa

    """
    LEVELS = Choices('success', 'info', 'warning', 'error')
    level = models.CharField(
        choices=LEVELS, default=LEVELS.info, max_length=20)

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=False,
        related_name='notifications',
        on_delete=models.CASCADE
    )
    unread = models.BooleanField(default=True, blank=False, db_index=True)

    actor_content_type = models.ForeignKey(
        ContentType, related_name='notify_actor', on_delete=models.CASCADE)
    actor_object_id = models.CharField(max_length=255)
    actor = GenericForeignKey('actor_content_type', 'actor_object_id')

    verb = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    target_content_type = models.ForeignKey(
        ContentType,
        related_name='notify_target',
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )
    target_object_id = models.CharField(max_length=255, blank=True, null=True)
    target = GenericForeignKey('target_content_type', 'target_object_id')

    action_object_content_type = models.ForeignKey(ContentType, blank=True, null=True,
                                                   related_name='notify_action_object', on_delete=models.CASCADE)
    action_object_object_id = models.CharField(
        max_length=255, blank=True, null=True)
    action_object = GenericForeignKey(
        'action_object_content_type', 'action_object_object_id')

    # The type of this notification object
    type = models.CharField(choices=NOTIFICATION_TYPES,
                            max_length=50, null=True, blank=True)

    # The category of this notification object
    NOTIFICATION_CATEGORY = Choices('normal', 'message')

    category = models.CharField(
        choices=NOTIFICATION_CATEGORY, default=NOTIFICATION_CATEGORY.normal, max_length=20)

    timestamp = models.DateTimeField(default=timezone.now)

    public = models.BooleanField(default=True, db_index=True)
    deleted = models.BooleanField(default=False, db_index=True)
    emailed = models.BooleanField(default=False, db_index=True)

    parent_notification = models.ForeignKey('self',
                                            default=None,
                                            null=True,
                                            related_name='child_notifications',
                                            on_delete=models.SET_NULL)

    data = JSONField(blank=True, null=True)
    objects = NotificationManager.from_queryset(NotificationQuerySet)()

    class Meta:
        ordering = ('-timestamp',)
        app_label = 'notifications'

    def render_plain_text(self):
        # TODO: Better format.
        return self.__str__()

    def __unicode__(self):
        ctx = {
            'actor': self.actor,
            'verb': self.verb,
            'action_object': self.action_object,
            'target': self.target,
            'timesince': self.timesince()
        }
        if self.target:
            if self.action_object:
                return u'%(actor)s %(verb)s %(action_object)s on %(target)s %(timesince)s ago' % ctx
            return u'%(actor)s %(verb)s %(target)s %(timesince)s ago' % ctx
        if self.action_object:
            return u'%(actor)s %(verb)s %(action_object)s %(timesince)s ago' % ctx
        return u'%(actor)s %(verb)s %(timesince)s ago' % ctx

    def email_format(self):
        ctx = {
            'actor': self.actor,
            'verb': self.verb,
            'action_object': self.action_object,
            'target': self.target,
            'date': dateformat.format(self.timestamp, 'D, M d Y h:m A')
        }
        if self.target:
            if self.action_object:
                return u'%(actor)s %(verb)s %(action_object)s on %(target)s on %(date)s' % ctx
            return u'%(actor)s %(verb)s %(target)s on %(date)s' % ctx
        if self.action_object:
            return u'%(actor)s %(verb)s %(action_object)s on %(date)s' % ctx
        return u'%(actor)s %(verb)s on %(date)s' % ctx

    def __str__(self):  # Adds support for Python 3
        return self.__unicode__()

    def timesince(self, now=None):
        """
        Shortcut for the ``django.utils.timesince.timesince`` function of the
        current timestamp.
        """
        from django.utils.timesince import timesince as timesince_
        return timesince_(self.timestamp, now)

    @property
    def slug(self):
        return id2slug(self.id)

    def mark_as_read(self):
        if self.unread:
            if self.child_notifications.count() == 0:
                self.unread = False
                parent_notification = self.parent_notification
                self.parent_notification = None
                self.save()

                # Update the parent
                if parent_notification:
                    if self.timestamp >= parent_notification.timestamp:
                        first_child_notification = parent_notification.child_notifications.first()
                        if first_child_notification:
                            parent_notification.timestamp = first_child_notification.timestamp
                            parent_notification.verb = first_child_notification.verb
                            parent_notification.actor = first_child_notification.actor
                            parent_notification.data = first_child_notification.data
                            parent_notification.type = first_child_notification.type

                    if parent_notification.child_notifications.count() == 0:
                        parent_notification.unread = False

                    parent_notification.save()

            elif self.child_notifications.count() == 1:
                self.unread = False
                child = self.child_notifications.first()
                child.parent_notification = None
                child.unread = False
                child.save()
                self.save()

    def mark_as_unread(self):
        if not self.unread:
            self.unread = True
            self.save()


def notify_handler(verb, **kwargs):
    """
    Handler function to create Notification instance upon action signal call.
    """

    # Pull the options out of kwargs
    kwargs.pop('signal', None)
    recipient = kwargs.pop('recipient')
    actor = kwargs.pop('sender')
    optional_objs = [
        (kwargs.pop(opt, None), opt)
        for opt in ('target', 'action_object')
    ]
    public = bool(kwargs.pop('public', True))
    description = kwargs.pop('description', None)
    timestamp = kwargs.pop('timestamp', timezone.now())
    level = kwargs.pop('level', Notification.LEVELS.info)
    type = kwargs.pop('type', None)
    category = kwargs.pop(
        'category', Notification.NOTIFICATION_CATEGORY.normal)
    send_email = kwargs.pop('send_email', True)
    send_telegram = kwargs.pop('send_telegram', False)
    push_notification_title = kwargs.pop(
        'push_notification_title', 'You have a new notification')
    push_notification_description = kwargs.pop(
        'push_notification_description', push_notification_title)
    # Check if User or Group
    if isinstance(recipient, Group):
        recipients = recipient.user_set.all()
    elif isinstance(recipient, (QuerySet, list)):
        recipients = recipient
    else:
        recipients = [recipient]

    new_notifications = []

    for recipient in recipients:
        newnotify = Notification(
            recipient=recipient,
            actor_content_type=ContentType.objects.get_for_model(actor),
            actor_object_id=actor.pk,
            verb=text_type(verb),
            public=public,
            category=category,
            description=description,
            timestamp=timestamp,
            level=level,
            type=type
        )

        target = None
        # Set optional objects
        for obj, opt in optional_objs:
            if obj is not None:
                target = obj
                setattr(newnotify, '%s_object_id' % opt, obj.pk)
                setattr(newnotify, '%s_content_type' % opt,
                        ContentType.objects.get_for_model(obj))

        if kwargs and EXTRA_DATA:
            newnotify.data = kwargs

        related_notification = Notification.objects.find_related_notifications(category=category,
                                                                               target=target,
                                                                               recipient=recipient)

        if related_notification:
            if related_notification.parent_notification:
                parent_notification = related_notification.parent_notification
                parent_notification.type = type
                parent_notification.actor = actor
                parent_notification.timestamp = timestamp
                parent_notification.verb = verb
                parent_notification.data = kwargs
                parent_notification.save()
            else:
                parent_notification = deepcopy(related_notification)
                parent_notification.pk = None
                parent_notification.type = type
                parent_notification.actor = actor
                parent_notification.timestamp = timestamp
                parent_notification.verb = verb
                parent_notification.data = kwargs
                parent_notification.save()

                related_notification.parent_notification = parent_notification
                related_notification.save()

            newnotify.parent_notification = parent_notification

        newnotify.save()
        new_notifications.append(newnotify)

        if recipient.email and send_email:
            send_mail(
                f'[Moogter] {push_notification_title}',
                newnotify.email_format(),
                settings.DEFAULT_FROM_EMAIL,
                [recipient.email],
                fail_silently=(not settings.DEBUG),
            )

        from chat.models import Conversation
        telegram = recipient.telegram_chat.first()
        if telegram and telegram.chat_id and telegram.enable_notifications \
                and newnotify.target_content_type != ContentType.objects.get_for_model(Conversation) and \
                send_telegram:

            bot.sendMessage(telegram.chat_id,
                            f'{push_notification_title}\n\n{push_notification_description}')

    send_fcm_notification(new_notifications[0], list(
        map(lambda u: u.recipient_id, new_notifications)), push_notification_title, push_notification_description)
    return new_notifications


# connect the signal
notify.connect(
    notify_handler, dispatch_uid='notifications.models.notification')
