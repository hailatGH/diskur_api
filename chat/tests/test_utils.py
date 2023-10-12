from django.test import TestCase

from api.tests.utility import create_user
from chat.models import Conversation, Participant, InvitationMessage, MessageSummary
from chat.utils import lock_conversation, unlock_conversation
from invitations.models import Invitation
from meda.tests.test_models import create_moogt
from chat.models import ModeratorInvitationMessage
from invitations.models import ModeratorInvitation


class CreateOrUpdateConversationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.moogt = create_moogt()
        cls.inviter = create_user(
            username='participant_inviter', password='pass123')
        cls.invitee = create_user(
            username='participant_invitee', password='pass123')
        cls.moderator = create_user(
            username='participant_moderator', password='pass123')

    def create_invitation(self):
        invitation = Invitation(
            moogt=self.moogt, invitee=self.invitee, inviter=self.inviter)
        invitation.save()
        return invitation

    def create_moderator_invitation(self):
        invitaion = self.create_invitation()
        moderator_invitation = ModeratorInvitation(
            moderator=self.moderator, invitation=invitaion)
        moderator_invitation.save()
        return moderator_invitation

    def test_receiver_creates_a_conversation(self):
        """
        It should create a Conversation object.
        """
        self.create_invitation()
        self.assertEqual(Conversation.objects.count(), 1)

    def test_adds_users_as_participants_in_a_conversation(self):
        """
        When a conversation is created, the participants should also be added.
        """
        self.create_invitation()
        proponent_exists = Participant.objects.filter(user=self.inviter,
                                                      role=Participant.ROLES.MOOGTER.value).exists()
        self.assertTrue(proponent_exists)
        opponent_exists = Participant.objects.filter(user=self.invitee,
                                                     role=Participant.ROLES.MOOGTER.value).exists()
        self.assertTrue(opponent_exists)

    def test_does_not_create_a_conversation_if_it_already_exists(self):
        """
        If a conversation exists between participants, it should not create a new one.
        """
        conversation = Conversation.objects.create()
        conversation.add_participant(user=self.inviter,
                                     role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(user=self.invitee,
                                     role=Participant.ROLES.MOOGTER.value)

        self.create_invitation()
        self.assertEqual(Conversation.objects.count(), 1)

    def test_creates_an_invitation_message_in_a_new_conversation(self):
        """
        If a new conversation is being created, it should add a new message to the conversation.
        """
        invitation = self.create_invitation()
        message = InvitationMessage.objects.get(invitation=invitation,
                                                user=self.inviter)
        self.assertIsNotNone(message)
        self.assertEqual(message.summaries.count(), 1)
        self.assertEqual(message.summaries.first().verb,
                         MessageSummary.VERBS.INVITE.value)

    def test_creates_an_invitation_message_in_an_existing_conversation(self):
        """
        If a conversation already exists, it should add a new message to the conversation.
        """
        conversation = Conversation.objects.create()
        conversation.add_participant(user=self.inviter,
                                     role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(user=self.invitee,
                                     role=Participant.ROLES.MOOGTER.value)

        invitation = self.create_invitation()

        message = InvitationMessage.objects.get(invitation=invitation,
                                                user=self.inviter)
        self.assertIsNotNone(message)

    def test_creates_moderator_invitation_message_in_a_conversation(self):
        """
        If a new conversation is being created, it should add a new message to the conversation.
        """
        moderator_invitation = self.create_moderator_invitation()
        message = ModeratorInvitationMessage.objects.get(moderator_invitation=moderator_invitation,
                                                         user=self.inviter)

        self.assertIsNotNone(message)
        self.assertIsNotNone(message.conversation)
        self.assertIsNotNone(message.conversation.last_message)

        self.assertEqual(message.summaries.count(), 1)
        self.assertEqual(message.summaries.first().verb,
                         MessageSummary.VERBS.MODERATE.value)

    def test_creates_moderator_invitation_message_in_an_existing_conversation(self):
        """
        If a conversation already exists, it should add a new message to the conversation.
        """
        conversation = Conversation.objects.create()
        conversation.add_participant(user=self.inviter,
                                     role=Participant.ROLES.MOOGTER.value)

        conversation.add_participant(
            user=self.moderator, role=Participant.ROLES.MOOGTER.value)

        moderator_invitation = self.create_moderator_invitation()

        message = ModeratorInvitationMessage.objects.get(moderator_invitation=moderator_invitation,
                                                         user=self.inviter)
        self.assertIsNotNone(message)
        self.assertIsNotNone(message.conversation)
        self.assertIsNotNone(message.conversation.last_message)

        self.assertEqual(message.summaries.count(), 1)
        self.assertEqual(message.summaries.first().verb,
                         MessageSummary.VERBS.MODERATE.value)

    def test_does_not_recreate_an_invitation_message_when_an_invitation_is_updated(self):
        """
        If an invitation is being updated a new invitation message should not be created.
        """
        invitation = self.create_invitation()

        # Update the invitation
        invitation.save()

        count = InvitationMessage.objects.count()
        self.assertEqual(count, 1)


class LockUnlockConversationTests(TestCase):
    def test_should_lock_a_conversation(self):
        """Should lock a conversation.
        """
        participant_1 = create_user('participant_1', 'pass123')
        participant_2 = create_user('participant_2', 'pass123')
        conversation = Conversation.objects.create()
        conversation.participants.create(user=participant_1)
        conversation.participants.create(user=participant_2)

        lock_conversation(participant_1, participant_2)
        conversation.refresh_from_db()

        self.assertTrue(conversation.is_locked)

    def test_should_unlock_a_conversation(self):
        """Should unlock a conversation.
        """
        participant_1 = create_user('participant_1', 'pass123')
        participant_2 = create_user('participant_2', 'pass123')
        conversation = Conversation.objects.create(is_locked=True)
        conversation.participants.create(user=participant_1)
        conversation.participants.create(user=participant_2)

        unlock_conversation(participant_1, participant_2)
        conversation.refresh_from_db()

        self.assertFalse(conversation.is_locked)
