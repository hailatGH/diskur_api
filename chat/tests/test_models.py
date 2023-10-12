from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from api.tests.utility import create_user, catch_signal, create_invitation, create_moogt_with_user
from chat.models import Conversation, Participant, InvitationMessage, RegularMessage, MiniSuggestionMessage
from chat.signals import post_message_save
from meda.enums import InvitationStatus
from meda.tests.test_models import create_moogt
from moogts.models import MoogtMiniSuggestion
from moogts.serializers import MoogtMiniSuggestionNotificationSerializer
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from invitations.serializers import InvitationNotificationSerializer


class ConversationModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        cls.participant = create_user(
            username='participant', password='pass123')
        cls.participant_two = create_user(
            username="participant_two", password="pass123")

    def test_add_participant_adds_a_participant(self):
        """
        When invoked, it should add a participant to the conversation.
        """
        self.conversation.add_participant(
            user=self.participant, role=Participant.ROLES.MOOGTER.value)

        self.assertEqual(self.conversation.participants.count(), 1)

    def test_add_participant_rejects_invalid_role(self):
        """
        It must not allow invalid roles.
        """
        self.assertRaises(ValidationError,
                          self.conversation.add_participant,
                          user=self.participant,
                          role='invalid role')
        self.assertEqual(self.conversation.participants.count(), 0)

    def test_get_pending_mini_suggestions(self):
        """
        test get_pending_mini_suggestions function must return only the pending mini suggestions
        """
        moogt = create_moogt()
        mini_suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt)
        message = MiniSuggestionMessage.objects.create(
            mini_suggestion=mini_suggestion, conversation=self.conversation)

        self.assertEqual(
            self.conversation.get_pending_mini_suggestions().count(), 1)


class InvitationMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        cls.user_one = create_user(username='participant', password='pass123')
        cls.user_two = create_user(
            username='participant_two', password='pass123')

        cls.conversation.add_participant(
            user=cls.user_one, role=Participant.ROLES.MOOGTER.value)
        cls.conversation.add_participant(
            user=cls.user_two, role=Participant.ROLES.MOOGTER.value)

        cls.moogt = create_moogt_with_user(
            cls.user_one, resolution='test resolution', opposition=cls.user_two)

    def test_sends_a_post_message_save_signal_after_save(self):
        """
        Should send a signal if successfully saved.
        """
        with catch_signal(post_message_save) as handler:
            invitation = create_invitation(self.moogt, InvitationStatus.accepted(), inviter=self.user_one,
                                           invitee=self.user_two)

        handler.assert_called_once_with(
            sender=mock.ANY,
            message=invitation.message,
            signal=post_message_save
        )

    def test_sends_notifications(self):
        """
        Should send a notification when an invitation object is created
        """
        with catch_signal(notify) as handler:
            invitation = create_invitation(self.moogt, InvitationStatus.accepted(), inviter=self.user_one,
                                           invitee=self.user_two)

        handler.assert_called_once_with(
            signal=notify,
            recipient=self.user_two,
            sender=self.user_one,
            verb='invited',
            send_email=True,
            type=NOTIFICATION_TYPES.invitation_sent,
            category=Notification.NOTIFICATION_CATEGORY.normal,
            action_object=invitation.message.conversation,
            send_telegram=True,
            target=invitation,
            timestamp=invitation.message.created_at,
            data={'invitation': InvitationNotificationSerializer(
                invitation).data},
            push_notification_title='You received a Moogt Invite!',
            push_notification_description=f'{self.user_one} invited you to a Moogt, "{self.moogt}"'
        )


class RegularMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        cls.participant = create_user(
            username='participant', password='pass123')
        cls.participant_two = create_user(
            username='participant_two', password='pass123')

    def test_sends_a_post_message_save_signal_after_save(self):
        """
        Should send a signal if successfully saved.
        """
        with catch_signal(post_message_save) as handler:
            message = RegularMessage.objects.create()

        handler.assert_called_once_with(
            sender=mock.ANY,
            message=message,
            signal=post_message_save
        )

    def test_sends_a_notification_signal_after_save(self):
        """
        Should send a signal if succesfully saved
        """
        self.conversation.add_participant(
            user=self.participant, role=Participant.ROLES.MOOGTER.value)
        self.conversation.add_participant(
            user=self.participant_two, role=Participant.ROLES.MOOGTER.value)

        with catch_signal(notify) as handler:
            original_message = RegularMessage.objects.create(
                conversation=self.conversation, user=self.participant)

        handler.assert_called_once_with(
            signal=notify,
            sender=self.participant,
            recipient=self.participant_two,
            verb='sent',
            send_email=False,
            target=original_message,
            action_object=self.conversation,
            send_telegram=False,
            timestamp=original_message.created_at,
            type=NOTIFICATION_TYPES.regular_message,
            category=Notification.NOTIFICATION_CATEGORY.message,
            data={},
            push_notification_title='You have got a new message',
            push_notification_description=f'{self.participant} sent you a message'

        )

    def test_reply_to_property_sets_the_message_being_replied(self):
        """
        The reply_to property should be set to the message being replied to.
        """
        original_message = RegularMessage.objects.create()
        reply_message = RegularMessage.objects.create()
        reply_message.reply_to = original_message
        self.assertEqual(
            reply_message.reply_to_regular_message, original_message)
        self.assertIsNone(reply_message.reply_to_invitation_message)
        self.assertIsNone(reply_message.reply_to_mini_suggestion_message)

        reply_message = RegularMessage.objects.create()
        original_invitation_message = InvitationMessage.objects.create()
        reply_message.reply_to = original_invitation_message
        self.assertEqual(reply_message.reply_to_invitation_message,
                         original_invitation_message)
        self.assertIsNone(reply_message.reply_to_regular_message)
        self.assertIsNone(reply_message.reply_to_mini_suggestion_message)

        reply_message = RegularMessage.objects.create()
        original_mini_suggestion_message = MiniSuggestionMessage.objects.create()
        reply_message.reply_to = original_mini_suggestion_message
        self.assertEqual(reply_message.reply_to_mini_suggestion_message,
                         original_mini_suggestion_message)
        self.assertIsNone(reply_message.reply_to_regular_message)
        self.assertIsNone(reply_message.reply_to_invitation_message)

    def test_reply_to_being_set_to_invalid_object(self):
        """
        It should raise a validation error, if being set to an invalid object
        """
        reply_message = RegularMessage.objects.create()
        with self.assertRaises(ValidationError):
            reply_message.reply_to = 'invalid'

    def test_reply_to_getter_works(self):
        """
        The getter should get the replied message.
        """
        original_message = RegularMessage.objects.create()
        reply_message = RegularMessage.objects.create()
        reply_message.reply_to = original_message
        self.assertEqual(reply_message.reply_to, original_message)

    def test_get_recipient(self):
        self.conversation.add_participant(
            user=self.participant, role=Participant.ROLES.MOOGTER.value)
        self.conversation.add_participant(
            user=self.participant_two, role=Participant.ROLES.MOOGTER.value)
        original_message = RegularMessage.objects.create(
            conversation=self.conversation, user=self.participant)

        self.assertEqual(original_message.get_recepient().user,
                         self.participant_two)


class MiniSuggestionMessageTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        cls.user = create_user(username='participant', password='pass123')
        cls.suggester = create_user(
            username='participant_two', password='pass123')

        cls.conversation.add_participant(
            user=cls.user, role=Participant.ROLES.MOOGTER.value)
        cls.conversation.add_participant(
            user=cls.suggester, role=Participant.ROLES.MOOGTER.value)

        cls.moogt = create_moogt_with_user(
            cls.user, resolution='test resolution', opposition=cls.suggester)
        cls.invitation = create_invitation(
            cls.moogt, inviter=cls.user, invitee=cls.suggester)

    def test_sends_a_post_message_save_signal_after_save(self):
        """
        Should send a signal if successfully saved.
        """
        with catch_signal(post_message_save) as handler:
            message = MiniSuggestionMessage.objects.create()

        handler.assert_called_once_with(
            sender=mock.ANY,
            message=message,
            signal=post_message_save
        )

    def test_sends_a_notification(self):
        """
        Should send a notification to the recipient
        """
        with catch_signal(notify) as handler:
            mini_suggestion = MoogtMiniSuggestion.objects.create(
                moogt=self.moogt, user=self.suggester)

        handler.assert_called_once_with(
            signal=notify,
            sender=self.suggester,
            recipient=self.user,
            verb='suggested',
            send_email=False,
            target=mini_suggestion,
            action_object=self.conversation,
            send_telegram=False,
            timestamp=mini_suggestion.message.created_at,
            type=NOTIFICATION_TYPES.mini_suggestion_new,
            category=Notification.NOTIFICATION_CATEGORY.normal,
            data={'mini_suggestion': MoogtMiniSuggestionNotificationSerializer(
                mini_suggestion).data},
            push_notification_title=None,
            push_notification_description=None
        )
