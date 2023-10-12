'''
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".
Replace this with more appropriate tests for your application.
'''
import json

import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.contrib.contenttypes.models import ContentType
# -*- coding: utf-8 -*-
# pylint: disable=too-many-lines,missing-docstring
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localtime, utc

from api.tests.utility import create_conversation, create_regular_message, \
    create_moogt_with_user, create_view, create_argument, create_poll
from notifications.enums import NOTIFICATION_TYPES
from notifications.models import Notification, notify_handler
from notifications.signals import notify
from notifications.utils import id2slug
from views.models import View
from arguments.models import Argument
from moogts.models import Moogt
from polls.models import Poll

User = get_user_model()

try:
    # Django >= 1.7
    from django.test import override_settings  # noqa
except ImportError:
    # Django <= 1.6
    from django.test.utils import override_settings  # noqa


class NotificationTest(TestCase):
    ''' Django notifications automated tests '''

    @override_settings(USE_TZ=True)
    @override_settings(TIME_ZONE='Asia/Shanghai')
    def test_use_timezone(self):
        from_user = User.objects.create(
            username="from", password="pwd", email="example@example.com")
        to_user = User.objects.create(
            username="to", password="pwd", email="example@example.com")
        notify.send(from_user, recipient=to_user,
                    verb='commented', action_object=from_user)
        notification = Notification.objects.get(recipient=to_user)
        delta = (
            timezone.now().replace(tzinfo=utc) - localtime(notification.timestamp,
                                                           pytz.timezone(settings.TIME_ZONE))
        )
        self.assertTrue(delta.seconds < 60)
        # The delta between the two events will still be less than a second despite the different timezones
        # The call to now and the immediate call afterwards will be within a short period of time, not 8 hours as the
        # test above was originally.

    @override_settings(USE_TZ=False)
    @override_settings(TIME_ZONE='Asia/Shanghai')
    def test_disable_timezone(self):
        from_user = User.objects.create(
            username="from2", password="pwd", email="example@example.com")
        to_user = User.objects.create(
            username="to2", password="pwd", email="example@example.com")
        notify.send(from_user, recipient=to_user,
                    verb='commented', action_object=from_user)
        notification = Notification.objects.get(recipient=to_user)
        delta = timezone.now() - notification.timestamp
        self.assertTrue(delta.seconds < 60)

    def test_send_email_argument_set_to_true(self):
        """
        If send_email is set to True sending a notification, make sure an email has been sent
        """
        from_user = User.objects.create(
            username="from2", password="pwd", email="example@example.com")
        to_user = User.objects.create(
            username="to2", password="pwd", email="example@example.com")
        notify.send(sender=from_user,
                    recipient=to_user,
                    verb="invited",
                    send_email=True)

        notification_exists = Notification.objects.filter(
            recipient=to_user).exists()
        self.assertTrue(notification_exists)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject,
                         "[Moogter] You have a new notification")

    def test_send_email_argument_set_to_false(self):
        """
        If send_email is set to False sending a notification, make sure an email will not be sent
        """
        from_user = User.objects.create(
            username="from2", password="pwd", email="example@example.com")
        to_user = User.objects.create(
            username="to2", password="pwd", email="example@example.com")
        notify.send(sender=from_user,
                    recipient=to_user,
                    verb="invited",
                    send_email=False)

        self.assertEqual(len(mail.outbox), 0)


class NotificationManagersTest(TestCase):
    ''' Django notifications Manager automated tests '''

    def setUp(self):
        self.message_count = 10
        self.other_user = User.objects.create(
            username="other1", password="pwd", email="example@example.com")

        self.from_user = User.objects.create(
            username="from2", password="pwd", email="example@example.com")
        self.to_user = User.objects.create(
            username="to2", password="pwd", email="example@example.com")
        self.to_group = Group.objects.create(name="to2_g")
        self.to_user_list = User.objects.all()
        self.to_group.user_set.add(self.to_user)
        self.to_group.user_set.add(self.other_user)

        for _ in range(self.message_count):
            notify.send(self.from_user, recipient=self.to_user,
                        verb='commented', action_object=self.from_user)
        # Send notification to group
        notify.send(self.from_user, recipient=self.to_group,
                    verb='commented', action_object=self.from_user)
        self.message_count += self.to_group.user_set.count()
        # Send notification to user list
        notify.send(self.from_user, recipient=self.to_user_list,
                    verb='commented', action_object=self.from_user)
        self.message_count += len(self.to_user_list)

        self.view = View.objects.create(
            content='test content', user=self.to_user)

    def test_notify_send_return_val(self):
        results = notify.send(self.from_user, recipient=self.to_user,
                              verb='commented', action_object=self.from_user)
        for result in results:
            if result[0] is notify_handler:
                self.assertEqual(len(result[1]), 1)
                # only check types for now
                self.assertEqual(type(result[1][0]), Notification)

    def test_notify_send_return_val_group(self):  # pylint: disable=invalid-name
        results = notify.send(self.from_user, recipient=self.to_group,
                              verb='commented', action_object=self.from_user)
        for result in results:
            if result[0] is notify_handler:
                self.assertEqual(
                    len(result[1]), self.to_group.user_set.count())
                for notification in result[1]:
                    # only check types for now
                    self.assertEqual(type(notification), Notification)

    def test_unread_manager(self):
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count)
        notification = Notification.objects.filter(
            recipient=self.to_user).first()
        notification.mark_as_read()
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count - 1)
        for notification in Notification.objects.unread():
            self.assertTrue(notification.unread)

    def test_read_manager(self):
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count)
        notification = Notification.objects.filter(
            recipient=self.to_user).first()
        notification.mark_as_read()
        self.assertEqual(Notification.objects.read().count(), 1)
        for notification in Notification.objects.read():
            self.assertFalse(notification.unread)

    def test_mark_all_as_read_manager(self):
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count)
        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        self.assertEqual(self.to_user.notifications.unread().count(), 0)

    def test_unread_messages_count(self):
        """
        Tests whether unread messages returns the correct number of unread messages in conversations
        and unread notifications return the correct number of unread notification
        """
        self.assertEqual(
            self.to_user.notifications.unread_messages().count(), 0)
        self.assertEqual(
            Notification.objects.unread_notifications().count(), self.message_count)

        conversation = create_conversation([self.from_user, self.to_user])
        message = create_regular_message(
            self.from_user, "test message", conversation)

        self.assertEqual(
            self.to_user.notifications.unread_messages().count(), 1)
        # the plus one is for the notification of the regular message that is being created
        self.assertEqual(
            Notification.objects.unread_notifications().count(), self.message_count)

    def test_mark_messages_as_read_manager(self):
        conversation = create_conversation([self.from_user, self.to_user])
        message = create_regular_message(
            self.from_user, "test message", conversation)

        self.assertEqual(
            self.to_user.notifications.unread_messages().count(), 1)

        Notification.objects.filter(
            recipient=self.to_user).mark_messages_as_read()
        self.assertEqual(
            self.to_user.notifications.unread_messages().count(), 0)

    @override_settings(DJANGO_NOTIFICATIONS_CONFIG={
        'SOFT_DELETE': True
    })  # pylint: disable=invalid-name
    def test_mark_all_as_read_manager_with_soft_delete(self):
        # even soft-deleted notifications should be marked as read
        # refer: https://github.com/django-notifications/django-notifications/issues/126
        to_delete = Notification.objects.filter(
            recipient=self.to_user).order_by('id')[0]
        to_delete.deleted = True
        to_delete.save()
        self.assertTrue(Notification.objects.filter(
            recipient=self.to_user).order_by('id')[0].unread)
        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        self.assertFalse(Notification.objects.filter(
            recipient=self.to_user).order_by('id')[0].unread)

    def test_mark_all_as_unread_manager(self):
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count)
        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        self.assertEqual(self.to_user.notifications.unread().count(), 0)
        Notification.objects.filter(
            recipient=self.to_user).mark_all_as_unread()
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count)

    def test_mark_all_deleted_manager_without_soft_delete(self):  # pylint: disable=invalid-name
        self.assertRaises(ImproperlyConfigured, Notification.objects.active)
        self.assertRaises(ImproperlyConfigured, Notification.objects.active)
        self.assertRaises(ImproperlyConfigured,
                          Notification.objects.mark_all_as_deleted)
        self.assertRaises(ImproperlyConfigured,
                          Notification.objects.mark_all_as_active)

    @override_settings(DJANGO_NOTIFICATIONS_CONFIG={
        'SOFT_DELETE': True
    })
    def test_mark_all_deleted_manager(self):
        notification = Notification.objects.filter(
            recipient=self.to_user).first()
        notification.mark_as_read()
        self.assertEqual(Notification.objects.read().count(), 1)
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count - 1)
        self.assertEqual(Notification.objects.active().count(),
                         self.message_count)
        self.assertEqual(Notification.objects.deleted().count(), 0)

        Notification.objects.mark_all_as_deleted()
        self.assertEqual(Notification.objects.read().count(), 0)
        self.assertEqual(Notification.objects.unread().count(), 0)
        self.assertEqual(Notification.objects.active().count(), 0)
        self.assertEqual(
            Notification.objects.deleted().count(), self.message_count)

        Notification.objects.mark_all_as_active()
        self.assertEqual(Notification.objects.read().count(), 1)
        self.assertEqual(Notification.objects.unread().count(),
                         self.message_count - 1)
        self.assertEqual(Notification.objects.active().count(),
                         self.message_count)
        self.assertEqual(Notification.objects.deleted().count(), 0)

    def test_find_related_notification_manager(self):
        notification = Notification.objects.create(actor=self.from_user,
                                                   recipient=self.to_user,
                                                   category=Notification.NOTIFICATION_CATEGORY.normal,
                                                   type=NOTIFICATION_TYPES.view_applaud,
                                                   verb="applauded",
                                                   target=self.view)
        related_notification = Notification.objects.find_related_notifications(
            recipient=self.to_user,
            category=Notification.NOTIFICATION_CATEGORY.normal,
            target=self.view
        )
        self.assertIsNotNone(related_notification)
        self.assertEqual(related_notification, notification)

        # With different category
        related_notification = Notification.objects.find_related_notifications(
            recipient=self.to_user,
            category=Notification.NOTIFICATION_CATEGORY.message,
            target=self.view
        )
        self.assertIsNone(related_notification)

        # With different target object
        related_notification = Notification.objects.find_related_notifications(
            recipient=self.to_user,
            category=Notification.NOTIFICATION_CATEGORY.normal,
            target=None
        )

        self.assertIsNone(related_notification)

        # With a notification that has a parent notification
        child_notification = Notification.objects.create(actor=self.from_user,
                                                         recipient=self.to_user,
                                                         category=Notification.NOTIFICATION_CATEGORY.normal,
                                                         type=NOTIFICATION_TYPES.view_applaud,
                                                         verb="applauded",
                                                         target=self.view,
                                                         parent_notification=notification)

        related_notification = Notification.objects.find_related_notifications(
            recipient=self.to_user,
            category=Notification.NOTIFICATION_CATEGORY.normal,
            target=self.view
        )

        self.assertEqual(related_notification, child_notification)
        self.assertNotEqual(related_notification, notification)


class NotificationTestPages(TestCase):
    ''' Django notifications automated page tests '''

    def setUp(self):
        self.message_count = 10
        self.from_user = User.objects.create_user(
            username="from", password="pwd", email="example@example.com")
        self.to_user = User.objects.create_user(
            username="to", password="pwd", email="example@example.com")
        self.to_user.is_staff = True
        self.to_user.save()
        for _ in range(self.message_count):
            notify.send(self.from_user,
                        recipient=self.to_user,
                        verb='commented',
                        action_object=self.from_user)

    def logout(self):
        self.client.post(reverse('admin:logout') + '?next=/', {})

    def login(self, user):
        self.client.force_login(user)

    def test_all_messages_page(self):
        self.login(self.to_user)
        response = self.client.get(reverse('notifications:all'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.all()))

    def test_unread_notifications_pages(self):
        self.login(self.to_user)
        response = self.client.get(reverse('notifications:unread'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.unread()))
        self.assertEqual(
            len(response.context['notifications']), self.message_count)

        for index, notification in enumerate(self.to_user.notifications.all()):
            if index % 3 == 0:
                response = self.client.get(
                    reverse('notifications:mark_as_read', args=[id2slug(notification.id)]))
                self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse('notifications:unread'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.unread()))
        self.assertTrue(
            len(response.context['notifications']) < self.message_count)

        response = self.client.get(reverse('notifications:mark_all_as_read'))
        self.assertRedirects(response, reverse('notifications:unread'))
        response = self.client.get(reverse('notifications:unread'))
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.unread()))
        self.assertEqual(len(response.context['notifications']), 0)

    def test_unread_notification_related_view_first(self):
        self.login(self.to_user)

        view_content_type = ContentType.objects.get_for_model(View)

        view = create_view(self.to_user, content="test resolution")
        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="applauded",
                    target=view)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb='commented',
                    action_object=self.from_user)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?related_to_me=true')
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['unread_list'][0]
                         ['target_content_type'], view_content_type.id)
        self.assertEqual(data['unread_list'][0]
                         ['target_object_id'], str(view.id))
        self.assertEqual(data['unread_list'][0]['verb'], 'applauded')
        self.assertEqual(data['unread_list'][0]['related_to_me'], True)

    def test_unread_notification_related_moogt_first(self):
        self.login(self.to_user)

        moogt_content_type = ContentType.objects.get_for_model(Moogt)

        moogt_owned = create_moogt_with_user(
            self.to_user, resolution="test resolution - owned moogt")
        moogt_following = create_moogt_with_user(
            self.from_user, resolution="test resolution - following moogt")

        moogt_following.followers.add(self.to_user)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="commented",
                    target=moogt_following)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="replied",
                    target=moogt_owned)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb='commented',
                    target=moogt_following)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?related_to_me=true')
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['unread_list'][0]
                         ['target_content_type'], moogt_content_type.id)
        self.assertEqual(data['unread_list'][0]
                         ['target_object_id'], str(moogt_owned.id))
        self.assertEqual(data['unread_list'][0]['verb'], 'replied')
        self.assertEqual(data['unread_list'][0]['related_to_me'], True)

        self.assertEqual(data['unread_list'][1]
                         ['target_content_type'], moogt_content_type.id)
        self.assertEqual(data['unread_list'][1]
                         ['target_object_id'], str(moogt_following.id))
        self.assertEqual(data['unread_list'][1]['verb'], 'commented')
        self.assertEqual(data['unread_list'][1]['related_to_me'], False)

    def test_unread_notification_related_argument_first(self):
        self.login(self.to_user)

        argument_content_type = ContentType.objects.get_for_model(Argument)
        argument = create_argument(self.to_user, "test argument")
        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="applauded",
                    target=argument)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb='commented',
                    action_object=self.from_user)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?related_to_me=true')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(data['unread_list'][0]
                         ['target_content_type'], argument_content_type.id)
        self.assertEqual(data['unread_list'][0]
                         ['target_object_id'], str(argument.id))
        self.assertEqual(data['unread_list'][0]['verb'], 'applauded')

    def test_unread_notification_related_poll_first(self):
        self.login(self.to_user)

        poll_content_type = ContentType.objects.get_for_model(Poll)
        poll_owned = create_poll(self.to_user, "poll title 1")
        poll_following = create_poll(self.from_user, "poll title 2")

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="commented",
                    target=poll_following)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="voted",
                    target=poll_owned)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="commented",
                    target=poll_following)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?related_to_me=true')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(data['unread_list'][0]
                         ['target_content_type'], poll_content_type.id)
        self.assertEqual(data['unread_list'][0]
                         ['target_object_id'], str(poll_owned.id))
        self.assertEqual(data['unread_list'][0]['verb'], 'voted')

    def test_mark_messages_as_read(self):
        self.login(self.to_user)
        # there are no notifications for new messages
        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?type=message')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data['unread_list']), 0)

        # create a message and notify recipient which creates a notification object
        conversation = create_conversation([self.from_user, self.to_user])
        message = create_regular_message(
            self.from_user, "test message", conversation)

        # there is a notification for new message
        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?type=message')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data['unread_list']), 1)

        response = self.client.get(
            reverse('notifications:live_mark_messages_as_read'))

        # mark message notifications as read
        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + '?type=message')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data['unread_list']), 0)

    def test_next_pages(self):
        self.login(self.to_user)
        query_parameters = '?var1=hello&var2=world'

        response = self.client.get(reverse('notifications:mark_all_as_read'), data={
            "next": reverse('notifications:unread') + query_parameters,
        })
        self.assertRedirects(response, reverse(
            'notifications:unread') + query_parameters)

        slug = id2slug(self.to_user.notifications.first().id)
        response = self.client.get(reverse('notifications:mark_as_read', args=[slug]), data={
            "next": reverse('notifications:unread') + query_parameters,
        })
        self.assertRedirects(response, reverse(
            'notifications:unread') + query_parameters)

        slug = id2slug(self.to_user.notifications.first().id)
        response = self.client.get(reverse('notifications:mark_as_unread', args=[slug]), {
            "next": reverse('notifications:unread') + query_parameters,
        })
        self.assertRedirects(response, reverse(
            'notifications:unread') + query_parameters)

    def test_delete_messages_pages(self):
        self.login(self.to_user)

        slug = id2slug(self.to_user.notifications.first().id)
        response = self.client.get(
            reverse('notifications:delete', args=[slug]))
        self.assertRedirects(response, reverse('notifications:all'))

        response = self.client.get(reverse('notifications:all'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.all()))
        self.assertEqual(
            len(response.context['notifications']), self.message_count - 1)

        response = self.client.get(reverse('notifications:unread'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.unread()))
        self.assertEqual(
            len(response.context['notifications']), self.message_count - 1)

    @override_settings(DJANGO_NOTIFICATIONS_CONFIG={
        'SOFT_DELETE': True
    })  # pylint: disable=invalid-name
    def test_soft_delete_messages_manager(self):
        self.login(self.to_user)

        slug = id2slug(self.to_user.notifications.first().id)
        response = self.client.get(
            reverse('notifications:delete', args=[slug]))
        self.assertRedirects(response, reverse('notifications:all'))

        response = self.client.get(reverse('notifications:all'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.active()))
        self.assertEqual(
            len(response.context['notifications']), self.message_count - 1)

        response = self.client.get(reverse('notifications:unread'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), len(
            self.to_user.notifications.unread()))
        self.assertEqual(
            len(response.context['notifications']), self.message_count - 1)

    def test_unread_count_api(self):
        self.login(self.to_user)

        response = self.client.get(
            reverse('notifications:live_unread_notification_count'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(list(data.keys()), [
                         'unread_following_moogt_cards', 'unread_user_moogt_cards', 'unread_notifications_count', 'unread_message_notifications_count', ])
        self.assertEqual(
            data['unread_notifications_count'], self.message_count)

        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        response = self.client.get(
            reverse('notifications:live_unread_notification_count'))
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(list(data.keys()), [
                         'unread_following_moogt_cards', 'unread_user_moogt_cards', 'unread_notifications_count', 'unread_message_notifications_count', ])

        self.assertEqual(data['unread_notifications_count'], 0)

        notify.send(self.from_user, recipient=self.to_user,
                    verb='commented', action_object=self.from_user)
        response = self.client.get(
            reverse('notifications:live_unread_notification_count'))
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(list(data.keys()), [
                         'unread_following_moogt_cards', 'unread_user_moogt_cards', 'unread_notifications_count', 'unread_message_notifications_count', ])
        self.assertEqual(data['unread_notifications_count'], 1)

    def test_all_count_api(self):
        self.login(self.to_user)

        response = self.client.get(
            reverse('notifications:live_all_notification_count'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(list(data.keys()), ['all_count'])
        self.assertEqual(data['all_count'], self.message_count)

        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        response = self.client.get(
            reverse('notifications:live_all_notification_count'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(list(data.keys()), ['all_count'])
        self.assertEqual(data['all_count'], self.message_count)

        notify.send(self.from_user, recipient=self.to_user,
                    verb='commented', action_object=self.from_user)
        response = self.client.get(
            reverse('notifications:live_all_notification_count'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(list(data.keys()), ['all_count'])
        self.assertEqual(data['all_count'], self.message_count + 1)

    def test_unread_list_api(self):
        self.login(self.to_user)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'unread_count', 'unread_list'])
        self.assertEqual(data['unread_count'], self.message_count)
        self.assertEqual(len(data['unread_list']), self.message_count)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list'), data={"max": 5})
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'unread_count', 'unread_list'])
        self.assertEqual(data['unread_count'], self.message_count)
        self.assertEqual(len(data['unread_list']), 5)

        # Test with a bad 'max' value
        response = self.client.get(reverse('notifications:live_unread_notification_list'), data={
            "max": "this_is_wrong",
        })
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'unread_count', 'unread_list'])
        self.assertEqual(data['unread_count'], self.message_count)
        self.assertEqual(len(data['unread_list']), self.message_count)

        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'unread_count', 'unread_list'])
        self.assertEqual(data['unread_count'], 0)
        self.assertEqual(len(data['unread_list']), 0)

        notify.send(self.from_user, recipient=self.to_user,
                    verb='commented', action_object=self.from_user)
        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'unread_count', 'unread_list'])
        self.assertEqual(data['unread_count'], 1)
        self.assertEqual(len(data['unread_list']), 1)
        self.assertEqual(data['unread_list'][0]['verb'], 'commented')
        self.assertEqual(data['unread_list'][0]['slug'],
                         id2slug(data['unread_list'][0]['id']))

    def test_all_list_api(self):
        self.login(self.to_user)

        response = self.client.get(
            reverse('notifications:live_all_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'all_count', 'all_list', 'has_next', 'has_prev'])
        self.assertEqual(data['all_count'], self.message_count)
        self.assertEqual(len(data['all_list']), self.message_count)

        response = self.client.get(
            reverse('notifications:live_all_notification_list'), data={"max": 5})
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'all_count', 'all_list', 'has_next', 'has_prev'])
        self.assertEqual(data['all_count'], self.message_count)
        self.assertEqual(len(data['all_list']), 5)

        # Test with a bad 'max' value
        response = self.client.get(reverse('notifications:live_all_notification_list'), data={
            "max": "this_is_wrong",
        })
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'all_count', 'all_list', 'has_next', 'has_prev'])
        self.assertEqual(data['all_count'], self.message_count)
        self.assertEqual(len(data['all_list']), self.message_count)

        Notification.objects.filter(recipient=self.to_user).mark_all_as_read()
        response = self.client.get(
            reverse('notifications:live_all_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'all_count', 'all_list', 'has_next', 'has_prev'])
        self.assertEqual(data['all_count'], self.message_count)
        self.assertEqual(len(data['all_list']), self.message_count)

        notify.send(self.from_user, recipient=self.to_user,
                    verb='commented', action_object=self.from_user)
        response = self.client.get(
            reverse('notifications:live_all_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(sorted(list(data.keys())), [
                         'all_count', 'all_list', 'has_next', 'has_prev'])
        self.assertEqual(data['all_count'], self.message_count + 1)
        self.assertEqual(len(data['all_list']), self.message_count)
        self.assertEqual(data['all_list'][0]['verb'], 'commented')
        self.assertEqual(data['all_list'][0]['slug'],
                         id2slug(data['all_list'][0]['id']))

    def test_unread_list_api_mark_as_read(self):  # pylint: disable=invalid-name
        self.login(self.to_user)
        num_requested = 3
        response = self.client.get(
            reverse('notifications:live_unread_notification_list'),
            data={"max": num_requested, "mark_as_read": 1}
        )
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['unread_count'],
                         self.message_count - num_requested)
        self.assertEqual(len(data['unread_list']), num_requested)
        response = self.client.get(
            reverse('notifications:live_unread_notification_list'),
            data={"max": num_requested, "mark_as_read": 1}
        )
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['unread_count'],
                         self.message_count - 2 * num_requested)
        self.assertEqual(len(data['unread_list']), num_requested)

    def test_live_update_tags(self):
        from django.shortcuts import render

        self.login(self.to_user)
        factory = RequestFactory()

        request = factory.get('/notification/live_updater')
        request.user = self.to_user

        render(request, 'notifications/test_tags.html', {'request': request})

        # TODO: Add more tests to check what is being output.

    def test_anon_user_gets_nothing(self):
        response = self.client.get(
            reverse('notifications:live_unread_notification_count'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['unread_notifications_count'], 0)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        self.assertEqual(response.status_code, 401)

    def test_mark_message_as_read(self):
        """
        Test if the mark message as read endpoint marks one notification as read
        """
        self.login(self.to_user)
        response = self.client.get(reverse('notifications:live_mark_as_read',
                                           kwargs={'pk': self.to_user.notifications.first().id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.to_user.notifications.unread().count(), self.message_count - 1)


class NotificationGroupingTests(TestCase):
    def setUp(self):
        self.from_user = User.objects.create_user(
            username="from", password="pwd", email="example@example.com")
        self.to_user = User.objects.create_user(
            username="to", password="pwd", email="example@example.com")
        self.to_user.is_staff = True
        self.to_user.save()
        self.view = View.objects.create(
            content='test content', user=self.to_user)

    def logout(self):
        self.client.post(reverse('admin:logout') + '?next=/', {})

    def login(self, user):
        self.client.force_login(user)

    def test_send_notification_creates_parent_and_child(self):
        self.login(self.to_user)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="applauded",
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.view_applaud,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    target=self.view)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="applauded",
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.view_applaud,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    target=self.view)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['unread_list']), 1)
        self.assertEqual(data['unread_list'][0]
                         ['child_notifications_count'], 2)
        self.assertEqual(data['unread_list'][0]['type'],
                         NOTIFICATION_TYPES.view_applaud)
        self.assertEqual(Notification.objects.count(), 3)

        notify.send(self.from_user,
                    recipient=self.to_user,
                    verb="agreed",
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.view_agree,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    target=self.view)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['unread_list']), 1)
        self.assertEqual(data['unread_list'][0]
                         ['child_notifications_count'], 3)
        self.assertEqual(data['unread_list'][0]['type'],
                         NOTIFICATION_TYPES.view_agree)
        self.assertEqual(Notification.objects.count(), 4)

    def test_get_notifications_in_group(self):
        self.login(self.to_user)

        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.normal,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          verb="applauded",
                                                          target=self.view)

        child_notification = Notification.objects.create(actor=self.from_user,
                                                         recipient=self.to_user,
                                                         category=Notification.NOTIFICATION_CATEGORY.normal,
                                                         type=NOTIFICATION_TYPES.view_agree,
                                                         verb="agreed",
                                                         target=self.view,
                                                         parent_notification=parent_notification)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['unread_list']), 1)
        self.assertEqual(data['unread_list'][0]['id'], parent_notification.id)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + f'?parent_id={parent_notification.id}')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['unread_list']), 1)
        self.assertEqual(data['unread_list'][0]['id'], child_notification.id)

        response = self.client.get(
            reverse('notifications:live_unread_notification_list') + f'?parent_id={child_notification.id}')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['unread_list']), 0)

    def test_unread_notifications_count(self):
        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.normal,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          verb="applauded",
                                                          target=self.view)

        child_notification = Notification.objects.create(actor=self.from_user,
                                                         recipient=self.to_user,
                                                         category=Notification.NOTIFICATION_CATEGORY.normal,
                                                         type=NOTIFICATION_TYPES.view_agree,
                                                         verb="agreed",
                                                         target=self.view,
                                                         parent_notification=parent_notification)

        count = self.to_user.notifications.unread_count(
            Notification.NOTIFICATION_CATEGORY.normal)
        self.assertEqual(count, 1)

        count = self.to_user.notifications.unread_count(
            Notification.NOTIFICATION_CATEGORY.message)
        self.assertEqual(count, 0)

    def test_mark_all_notifications_as_read(self):
        self.login(self.to_user)

        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.normal,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          verb="applauded",
                                                          target=self.view)

        Notification.objects.create(actor=self.from_user,
                                    recipient=self.to_user,
                                    category=Notification.NOTIFICATION_CATEGORY.normal,
                                    type=NOTIFICATION_TYPES.view_agree,
                                    verb="agreed",
                                    target=self.view,
                                    parent_notification=parent_notification)

        self.client.get(reverse('notifications:live_mark_all_as_read'))
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 0)

        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.message,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          target=self.view)

        Notification.objects.create(actor=self.from_user,
                                    recipient=self.to_user,
                                    category=Notification.NOTIFICATION_CATEGORY.message,
                                    target=self.view,
                                    parent_notification=parent_notification)

        self.client.get(reverse('notifications:live_mark_messages_as_read'))
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 0)

        parent_notification.unread = True
        parent_notification.save()

        Notification.objects.create(actor=self.from_user,
                                    recipient=self.to_user,
                                    category=Notification.NOTIFICATION_CATEGORY.message,
                                    target=self.view,
                                    parent_notification=parent_notification)
        Notification.objects.create(actor=self.from_user,
                                    recipient=self.to_user,
                                    category=Notification.NOTIFICATION_CATEGORY.message,
                                    target=self.view)
        self.client.get(reverse('notifications:live_mark_all_as_read') +
                        f'?parent_id={parent_notification.id}')
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 1)

    def test_mark_notification_as_read(self):
        self.login(self.to_user)

        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.normal,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          verb="applauded",
                                                          target=self.view)

        child1 = Notification.objects.create(actor=self.from_user,
                                             recipient=self.to_user,
                                             category=Notification.NOTIFICATION_CATEGORY.normal,
                                             type=NOTIFICATION_TYPES.view_agree,
                                             verb="agreed",
                                             target=self.view,
                                             parent_notification=parent_notification)

        child2 = Notification.objects.create(actor=self.from_user,
                                             recipient=self.to_user,
                                             category=Notification.NOTIFICATION_CATEGORY.normal,
                                             type=NOTIFICATION_TYPES.view_disagree,
                                             verb="disagreed",
                                             target=self.view,
                                             parent_notification=parent_notification)

        self.client.get(reverse('notifications:live_mark_as_read',
                        kwargs={'pk': parent_notification.id}))
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 3)
        self.client.get(
            reverse('notifications:live_mark_as_read', kwargs={'pk': child2.id}))
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 2)
        parent_notification.refresh_from_db()
        self.assertEqual(parent_notification.timestamp, child1.timestamp)
        self.assertEqual(parent_notification.verb, child1.verb)
        self.client.get(
            reverse('notifications:live_mark_as_read', kwargs={'pk': child1.id}))
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 0)
        child2.refresh_from_db()
        self.assertIsNone(child2.parent_notification)

        child3 = Notification.objects.create(actor=self.from_user,
                                             recipient=self.to_user,
                                             category=Notification.NOTIFICATION_CATEGORY.normal,
                                             type=NOTIFICATION_TYPES.view_comment,
                                             verb="commented",
                                             target=self.view,
                                             parent_notification=parent_notification)
        parent_notification.unread = True
        parent_notification.save()
        self.client.get(reverse('notifications:live_mark_as_read',
                        kwargs={'pk': parent_notification.id}))
        self.assertEqual(self.to_user.notifications.filter(
            unread=True).count(), 0)

    def test_all_list_does_not_include_parent_notification(self):
        self.login(self.to_user)

        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.normal,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          verb="applauded",
                                                          target=self.view)

        child1 = Notification.objects.create(actor=self.from_user,
                                             recipient=self.to_user,
                                             category=Notification.NOTIFICATION_CATEGORY.normal,
                                             type=NOTIFICATION_TYPES.view_agree,
                                             verb="agreed",
                                             target=self.view,
                                             parent_notification=parent_notification)

        response = self.client.get(
            reverse('notifications:live_all_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['all_list']), 1)
        self.assertEqual(data['all_list'][0]['id'], child1.id)

    def test_all_list_pagination(self):
        self.login(self.to_user)

        parent_notification = Notification.objects.create(actor=self.from_user,
                                                          recipient=self.to_user,
                                                          category=Notification.NOTIFICATION_CATEGORY.normal,
                                                          type=NOTIFICATION_TYPES.view_applaud,
                                                          verb="applauded",
                                                          target=self.view)

        for _ in range(11):
            Notification.objects.create(actor=self.from_user,
                                        recipient=self.to_user,
                                        category=Notification.NOTIFICATION_CATEGORY.normal,
                                        type=NOTIFICATION_TYPES.view_agree,
                                        verb="agreed",
                                        target=self.view,
                                        parent_notification=parent_notification)

        response = self.client.get(
            reverse('notifications:live_all_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['all_list']), 10)
        self.assertEqual(data['all_list'][0]['child_notifications_count'], 0)
        self.assertTrue(data['has_next'])
        self.assertFalse(data['has_prev'])

        response = self.client.get(
            reverse('notifications:live_all_notification_list') + '?page=2')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(data['all_list']), 1)


class NotificationTestExtraData(TestCase):
    ''' Django notifications automated extra data tests '''

    def setUp(self):
        self.message_count = 1
        self.from_user = User.objects.create_user(
            username="from", password="pwd", email="example@example.com")
        self.to_user = User.objects.create_user(
            username="to", password="pwd", email="example@example.com")
        self.to_user.is_staff = True
        self.to_user.save()
        for _ in range(self.message_count):
            notify.send(
                self.from_user,
                recipient=self.to_user,
                verb='commented',
                action_object=self.from_user,
                url="/learn/ask-a-pro/q/test-question-9/299/",
                other_content="Hello my 'world'"
            )

    def logout(self):
        self.client.post(reverse('admin:logout') + '?next=/', {})

    def login(self, user):
        self.client.force_login(user)

    def test_extra_data(self):
        self.login(self.to_user)
        response = self.client.get(
            reverse('notifications:live_unread_notification_list'))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['unread_list'][0]['data']['url'],
                         "/learn/ask-a-pro/q/test-question-9/299/")
        self.assertEqual(data['unread_list'][0]['data']
                         ['other_content'], "Hello my 'world'")


class TagTest(TestCase):
    ''' Django notifications automated tags tests '''

    def setUp(self):
        self.message_count = 1
        self.from_user = User.objects.create_user(
            username="from", password="pwd", email="example@example.com")
        self.to_user = User.objects.create_user(
            username="to", password="pwd", email="example@example.com")
        self.to_user.is_staff = True
        self.to_user.save()
        for _ in range(self.message_count):
            notify.send(
                self.from_user,
                recipient=self.to_user,
                verb='commented',
                action_object=self.from_user,
                url="/learn/ask-a-pro/q/test-question-9/299/",
                other_content="Hello my 'world'"
            )

    def tag_test(self, template, context, output):
        t = Template('{% load notifications_tags %}' + template)
        c = Context(context)
        self.assertEqual(t.render(c), output)

    def test_has_notification(self):
        template = "{{ user|has_notification }}"
        context = {"user": self.to_user}
        output = u"True"
        self.tag_test(template, context, output)
