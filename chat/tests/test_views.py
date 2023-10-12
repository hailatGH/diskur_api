from meda.tests.test_models import create_moogt
from chat.tests.utility import create_mini_suggestion_message
from chat.models import Conversation, Participant, InvitationMessage, MiniSuggestionMessage, RegularMessage
from chat.enums import ConversationType, MessageType
from api.tests.utility import create_user_and_login, create_user, create_conversation, create_regular_message, \
    create_invitation
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from api.tests.utility import create_moderator_invitation
from chat.models import ModeratorInvitationMessage
from meda.enums import ModeratorInvititaionStatus


class SendRegularMessageApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:chat:send_message', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_success(self):
        """
        Send a regular message successfully
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        conversation = create_conversation([user, user_1])

        response = self.post(
            {'conversation': conversation.id, 'content': 'test content'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], 'test content')
        self.assertEqual(response.data['conversation'], conversation.id)
        self.assertEqual(response.data['user_id'], user.id)

    def test_last_message(self):
        """
        test whether last message is updated successfully.
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        conversation = create_conversation([user, user_1])

        response = self.post(
            {'conversation': conversation.id, 'content': 'test content'})

        conversation.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(conversation.last_message, 'test content')

    def test_no_previous_conversation(self):
        """
        test creating a conversation if no conversation has been made between the two users
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        response = self.post({'content': 'test content', 'to': user_1.pk})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], 'test content')
        self.assertIsNotNone(response.data['conversation'])
        self.assertEqual(response.data['user_id'], user.id)

    def test_no_previous_conversation_last_message(self):
        """
        test whether last message is set when conversation is created
        """
        user_1 = create_user('username', 'password')
        user = create_user_and_login(self)

        response = self.post({'content': 'test content', 'to': user_1.pk})

        conversation = Conversation.objects.get(
            pk=response.data['conversation'])

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(conversation.last_message, 'test content')

    def test_non_existing_user_with_no_previous_conversation(self):
        """
        test if a non existent user has been passed to create a new conversation
        """
        user = create_user_and_login(self)

        response = self.post({'content': 'test content', 'to': user.pk + 1})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_user_with_no_previous_conversation(self):
        """
        test if no user has been passed to create a new conversation
        """
        user = create_user_and_login(self)

        response = self.post({'content': 'test content'})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_should_not_be_able_to_send_messages_in_a_locked_conversation(self):
        """Should not allow users to send a message in a locked conversation.
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        conversation = create_conversation([user, user_1])
        conversation.is_locked = True
        conversation.save()

        response = self.post(
            {'conversation': conversation.id, 'content': 'test content'})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ListMessageApiViewTests(APITestCase):
    def get(self, pk):
        url = reverse('api:chat:message_list', kwargs={
                      'version': 'v1', 'pk': pk})
        return self.client.get(url)

    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        participant_user = create_user(
            username='participant_user', password='testpassword')
        cls.moderator = create_user(
            username='participant_moderator', password='testpassword')
        cls.conversation.add_participant(
            user=participant_user, role=Participant.ROLES.MOOGTER.value)
        cls.invitation = create_invitation(create_moogt())
        cls.invitation_message = InvitationMessage.objects.create(conversation=cls.conversation,
                                                                  invitation=cls.invitation)

        cls.conversation_two = Conversation.objects.create()

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.conversation.add_participant(
            user=self.user, role=Participant.ROLES.MOOGTER.value)

    def test_none_existing_conversation(self):
        """
        If a conversation doesn't exist, it should respond with a not found response.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_none_participant_of_a_conversation_should_be_denied(self):
        """
        A none participant of a conversation is not allowed to browse messages in a conversation
        which he/she is not part of.
        """
        response = self.get(self.conversation_two.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_should_get_messages_in_a_conversation(self):
        """
        It should get the list of messages in a particular conversation.
        """
        response = self.get(self.conversation.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['pk'], self.invitation_message.id)
        self.assertEqual(response.data['results']
                         [0]['type'], 'invitation_message')
        self.assertIsNotNone(
            response.data['results'][0]['object']['summaries'])

    def test_should_get_mini_suggestion_messages_in_a_conversation(self):
        """
        It should get the list of mini suggestion messages in a particular conversation.
        """
        self.mini_suggestion_message = MiniSuggestionMessage.objects.create(
            conversation=self.conversation)

        inviter = create_user('inviter', 'pass123')
        invitee = create_user('invitee', 'pass123')
        self.mini_suggestion_message.invitee = invitee
        self.mini_suggestion_message.inviter = inviter
        self.mini_suggestion_message.save()

        response = self.get(self.conversation.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]
                         ['pk'], self.mini_suggestion_message.id)
        self.assertEqual(response.data['results']
                         [0]['type'], 'mini_suggestion_message')
        self.assertEqual(response.data['results']
                         [0]['object']['inviter_id'], inviter.id)
        self.assertEqual(response.data['results']
                         [0]['object']['invitee_id'], invitee.id)

    def test_should_get_moderator_invitation_message_in_a_conversation(self):
        moderator_invitation = create_moderator_invitation(
            moderator=self.moderator, invitation=self.invitation)

        self.moderator_invitation_message = ModeratorInvitationMessage.objects.create(conversation=self.conversation,
                                                                                      moderator_invitation=moderator_invitation
                                                                                      )

        inviter = create_user('inviter', 'pass123')
        invitee = create_user('invitee', 'pass123')
        self.invitation.inviter = inviter
        self.invitation.invitee = invitee

        self.invitation.save()

        response = self.get(self.conversation.id)

        self.assertEqual(response.data['results']
                         [0]['type'], 'moderator_invitation_message')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]
                         ['pk'], self.moderator_invitation_message.id)
        self.assertEqual(response.data['results']
                         [0]['object']['moderator_invitation']['invitation']['inviter_id'], inviter.id)
        self.assertEqual(response.data['results']
                         [0]['object']['moderator_invitation']['invitation']['invitee_id'], invitee.id)
        self.assertEqual(response.data['results']
                         [0]['object']['moderator_invitation']['status'], ModeratorInvititaionStatus.PENDING.name)

        self.assertIsNotNone(
            response.data['results'][0]['object']['summaries'])

    def test_should_get_tags(self):
        """
        It should get the list of tags if a mini suggestion is for changing tags.
        """
        message = create_mini_suggestion_message(conversation=self.conversation,
                                                 user=self.user)
        message.mini_suggestion.add_tags([{'name': 'tag 1'}])

        response = self.get(self.conversation.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['object']
                         ['mini_suggestion']['tags'][0]['name'], 'tag 1')

    def test_should_indicate_read_messages_in_a_conversation(self):
        """
        If a message is read by the user previously it should have is_read value true in the response
        """
        self.invitation_message.is_read = True
        self.invitation_message.save()

        response = self.get(self.conversation.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['object']['is_read'], True)

    def test_should_indicate_unread_messages_in_a_conversation(self):
        """
        If a message is not read by the user previously it should have is_read value false in the reponse
        """
        response = self.get(self.conversation.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['object']['is_read'], False)

    def test_check_count_of_message_list_after_message_delete(self):
        """
        If a message is deleted after the call to delete message endpoint
        """
        message = create_regular_message(
            user=self.user, content="Hello", conversation=self.conversation)

        first_response = self.get(self.conversation.id)

        message.delete()

        second_response = self.get(self.conversation.id)

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            first_response.data['count'], second_response.data['count'] + 1)

    def test_should_include_replied_message(self):
        """If there is a replied message, it should be included in the response."""
        regular_message = RegularMessage.objects.create(
            conversation=self.conversation)
        regular_message.reply_to = self.invitation_message
        regular_message.save()
        response = self.get(self.conversation.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['object']['reply_to_invitation_message_id'],
                         self.invitation_message.id)
        self.assertIsNotNone(response.data['results'][0]['object']['reply_to_invitation_message']['id'],
                             self.invitation_message.id)
        self.assertEqual(response.data['results'][0]['object']['conversation'],
                         self.conversation.id)


class ListConversationApiViewTests(APITestCase):
    def get(self, type=None):
        url = reverse('api:chat:conversation_list', kwargs={
                      'version': 'v1'}) + '?type=' + type
        return self.client.get(url, format='json')

    @classmethod
    def setUpTestData(cls):
        cls.conversation: Conversation = Conversation.objects.create()
        cls.participant_user = create_user(
            username='participant_user', password='testpassword')
        cls.conversation.add_participant(
            user=cls.participant_user, role=Participant.ROLES.MOOGTER.value)
        # a conversation should have messages to be shown in priority conversation list
        cls.reg_message = create_regular_message(
            cls.participant_user, "test message", cls.conversation)

        cls.conversation_two: Conversation = Conversation.objects.create()

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.conversation.add_participant(
            user=self.user, role=Participant.ROLES.MOOGTER.value)

    def test_success_in_priority_list(self):
        """
        test if a user's conversation is in priority list their conversation should be in the priority response
        """
        self.user.priority_conversations.add(self.conversation)

        response = self.get(type=ConversationType.PRIORITY.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['id'], self.conversation.id)

    def test_if_a_user_doesnt_follow_it_shouldnt_be_in_priority_list(self):
        """
        test if a user's conversation is not in the priority list or following it shouldn't be in the priority response
        """
        response = self.get(type=ConversationType.PRIORITY.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_multiple_conversation_in_priority_list(self):
        """
        test if a user's multple conversations are in priority list they should be in the priority response
        """
        participant_user_2 = create_user(
            username='participant_user2', password='testpassword')
        self.conversation_two.add_participant(
            user=participant_user_2, role=Participant.ROLES.MOOGTER.value)
        self.conversation_two.add_participant(
            user=self.user, role=Participant.ROLES.MOOGTER.value)

        self.user.priority_conversations.add(self.conversation)
        self.user.priority_conversations.add(self.conversation_two)

        reg_message = create_regular_message(
            participant_user_2, "test message", self.conversation_two)

        response = self.get(type=ConversationType.PRIORITY.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results']
                         [0]['id'], self.conversation_two.id)
        self.assertEqual(response.data['results']
                         [1]['id'], self.conversation.id)

    def test_following_and_in_priority(self):
        """
        test if a user is following the other user and in priority list it should be in the priorirty response
        """
        self.conversation.add_participant(
            user=self.participant_user, role=Participant.ROLES.MOOGTER.value)

        self.user.priority_conversations.add(self.conversation)
        self.user.following.add(self.participant_user)

        response = self.get(type=ConversationType.PRIORITY.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_general_conversation_list(self):
        """
        test if a user is not following or not in priority list it should be in the general response
        """
        response = self.get(type=ConversationType.GENERAL.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_unread_messages_count(self):
        """
        test if there are messages are unread their count should be in the response of conversations
        """
        inv_message = InvitationMessage.objects.create(
            conversation=self.conversation)
        sug_message = MiniSuggestionMessage.objects.create(
            conversation=self.conversation)
        self.conversation.last_message = "Mini Suggestion"
        self.conversation.save()

        response = self.get(type=ConversationType.GENERAL.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['id'], self.conversation.id)
        self.assertEqual(response.data['results'][0]['unread_count'], 3)

    def test_read_and_unread_messages_count(self):
        """
        test if there are read and unread messages the unread messages should be in the response of the conversation
        """
        invitation = create_invitation(create_moogt("resolution"))
        inv_message = InvitationMessage.objects.create(conversation=self.conversation,
                                                       invitation=invitation,
                                                       content=invitation.moogt.resolution)
        sug_message = MiniSuggestionMessage.objects.create(
            conversation=self.conversation)

        self.reg_message.is_read = True
        self.reg_message.save()
        inv_message.is_read = True
        inv_message.save()

        response = self.get(type=ConversationType.GENERAL.value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['id'], self.conversation.id)
        self.assertEqual(response.data['results'][0]['unread_count'], 1)


class ReadMessageApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:chat:read_message', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        cls.participant_user = create_user(
            username='participant_user', password='testpassword')
        cls.conversation.add_participant(
            user=cls.participant_user, role=Participant.ROLES.MOOGTER.value)

        cls.conversation_two = Conversation.objects.create()

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.conversation.add_participant(
            user=self.user, role=Participant.ROLES.MOOGTER.value)

    def test_success(self):
        """
        Marks a message as read if request is successful.
        """
        message = create_regular_message(
            user=self.participant_user, content="", conversation=self.conversation)

        response = self.post(
            {'conversation': self.conversation.pk, 'read_before_date': message.created_at})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        message.refresh_from_db()
        self.assertTrue(message.has_been_read_by(self.user))

    def test_read_a_message_again(self):
        """
        if a message is read again it should not add the user twice
        """
        message = create_regular_message(
            user=self.participant_user, content="", conversation=self.conversation)

        response = self.post(
            {'conversation': self.conversation.pk, 'read_before_date': message.created_at})
        response = self.post(
            {'conversation': self.conversation.pk, 'read_before_date': message.created_at})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        message.refresh_from_db()
        self.assertEqual(message.has_been_read_by(self.user), True)

    def test_mark_previous_messages_as_read(self):
        """
        If there are messages that are not read before read_before_date, they should be marked as
        read
        """
        earlier_message = create_regular_message(
            user=self.participant_user, content="", conversation=self.conversation)
        recent_message = create_regular_message(
            user=self.participant_user, content="", conversation=self.conversation)
        response = self.post({'conversation': self.conversation.pk,
                             'read_before_date': recent_message.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        earlier_message.refresh_from_db()
        self.assertTrue(earlier_message.has_been_read_by(self.user))

    def test_marks_previous_invitation_message_as_read(self):
        """
        If there are invitation messages that have not been read before read_before_date, they should be
        marked as read
        """
        earlier_message = InvitationMessage.objects.create(
            conversation=self.conversation)
        recent_message = InvitationMessage.objects.create(
            conversation=self.conversation)
        response = self.post({'conversation': self.conversation.pk,
                             'read_before_date': recent_message.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        earlier_message.refresh_from_db()
        self.assertTrue(earlier_message.has_been_read_by(self.user))

    def test_marks_previous_mini_suggestion_message_as_read(self):
        """
        If there are mini suggestion messages that have not been read before read_before_date, they should be
        marked as read
        """
        earlier_message = MiniSuggestionMessage.objects.create(
            conversation=self.conversation)
        recent_message = MiniSuggestionMessage.objects.create(
            conversation=self.conversation)
        response = self.post({'conversation': self.conversation.pk,
                             'read_before_date': recent_message.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        earlier_message.refresh_from_db()
        self.assertTrue(earlier_message.has_been_read_by(self.user))

    def test_mark_as_read_for_message_creator(self):
        """
        A message creator will not mark his own messages as read, therefore it shouldn't
        modify the is_read value.
        """
        message = RegularMessage.objects.create(
            user=self.user, conversation=self.conversation)
        response = self.post(
            {'conversation': self.conversation.pk, 'read_before_date': message.created_at})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        message.refresh_from_db()
        self.assertFalse(message.is_read)


class GetConversationWithSomeoneTests(APITestCase):
    def get(self, pk):
        url = reverse('api:chat:get_conversation_with_someone',
                      kwargs={'version': 'v1', 'pk': pk})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """
        A non authenticated request should be dealt with a not authorized response.
        """
        self.client.logout()
        response = self.get(1)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_pk(self):
        """
        A non existing user id in the request url should be dealt with a not found response.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_existing_user(self):
        """
        If there is an existing user that has a conversation with the user, it should respond with that
        conversation.
        """
        participant_user = create_user('participant_user', 'test123')
        conversation = Conversation.objects.create()
        conversation.add_participant(
            participant_user, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            self.user, role=Participant.ROLES.MOOGTER.value)

        response = self.get(participant_user.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], conversation.id)

    def test_non_existing_user(self):
        """
        If there is no conversation with a user, then that conversation should be created and it should
        respond with created.
        """
        participant_user = create_user('participant_user', 'test123')

        response = self.get(participant_user.id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        conversation = Conversation.objects.get(pk=response.data['id'])
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.participants.count(), 2)


class PrioritizeConversationTests(APITestCase):
    def get(self, pk):
        url = reverse('api:chat:prioritize_conversations',
                      kwargs={'version': 'v1', 'pk': pk})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """
        A non authenticated request should be dealt with a not authorized response.
        """
        self.client.logout()
        response = self.get(1)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_conversation_pk(self):
        """
        A non existing conversation id in the request url should be dealt with a not found response.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_existing_participant(self):
        """
        If the user is not a paticipant in the conversation, it should respond with forbidden.
        """
        participant_user = create_user('participant_user', 'test123')
        participant_user_1 = create_user('participant_user_1', 'test123')
        conversation = Conversation.objects.create()
        conversation.add_participant(
            participant_user, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            participant_user_1, role=Participant.ROLES.MOOGTER.value)

        response = self.get(conversation.id)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_existing_participant(self):
        """
        If the user is a participant in the conversation, it should add the conversation
        to the priority list and respond with ok and the conversation object.
        """
        participant_user = create_user('participant_user', 'test123')
        conversation = Conversation.objects.create()
        conversation.add_participant(
            participant_user, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            self.user, role=Participant.ROLES.MOOGTER.value)

        response = self.get(conversation.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], conversation.id)
        self.assertEqual(self.user.priority_conversations.count(), 1)


class UnPrioritizeConversationTests(APITestCase):
    def get(self, pk):
        url = reverse('api:chat:unprioritize_conversations',
                      kwargs={'version': 'v1', 'pk': pk})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """
        A non authenticated request should be dealt with a not authorized response.
        """
        self.client.logout()
        response = self.get(1)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_conversation_pk(self):
        """
        A non existing conversation id in the request url should be dealt with a not found response.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_existing_participant(self):
        """
        If the user is not a paticipant in the conversation, it should respond with forbidden.
        """
        participant_user = create_user('participant_user', 'test123')
        participant_user_1 = create_user('participant_user_1', 'test123')
        conversation = Conversation.objects.create()
        conversation.add_participant(
            participant_user, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            participant_user_1, role=Participant.ROLES.MOOGTER.value)

        response = self.get(conversation.id)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_conversation_not_prioritized(self):
        """
        If the conversation is not in the users priority list , it should respond with bad request.
        """
        participant_user = create_user('participant_user', 'test123')
        conversation = Conversation.objects.create()
        conversation.add_participant(
            participant_user, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            self.user, role=Participant.ROLES.MOOGTER.value)

        response = self.get(conversation.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_conversation_prioritized(self):
        """
        If the conversation is in the users priority list , it should respond with ok and the conversation object.
        """
        participant_user = create_user('participant_user', 'test123')
        conversation = Conversation.objects.create()
        conversation.add_participant(
            participant_user, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            self.user, role=Participant.ROLES.MOOGTER.value)
        self.user.priority_conversations.add(conversation)

        response = self.get(conversation.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], conversation.id)


class DeleteMessageApiViewTests(APITestCase):
    def get(self, pk):
        url = reverse('api:chat:delete_message', kwargs={
                      'version': 'v1', 'pk': pk})
        return self.client.get(url)

    @classmethod
    def setUpTestData(cls):
        cls.conversation = Conversation.objects.create()
        cls.participant_user = create_user(
            username='participant_user', password='testpassword')
        cls.conversation.add_participant(
            user=cls.participant_user, role=Participant.ROLES.MOOGTER.value)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.conversation.add_participant(
            user=self.user, role=Participant.ROLES.MOOGTER.value)

    def test_success(self):
        """
        If the request is successful
        """
        message = create_regular_message(
            user=self.user, content="Hello", conversation=self.conversation)

        response = self.get(message.pk)

        self.conversation.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(self.conversation.last_message, "")

    def test_mid_message_delete(self):
        """
            Tests if multiple messages are sent and the last one is deleted 
            the last_message must shift to the older message
        """

        message1 = create_regular_message(
            user=self.user, content="Hello", conversation=self.conversation)
        message2 = create_regular_message(
            user=self.user, content="World", conversation=self.conversation)
        message3 = create_regular_message(
            user=self.user, content="Selamta", conversation=self.conversation)

        response = self.get(message3.pk)

        self.conversation.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.conversation.last_message, message2.content)

    def test_last_message_delete(self):
        """
            Tests if multiple messages are sent and one of the first two is deleted 
            the last_message must stay the same
        """

        message1 = create_regular_message(
            user=self.user, content="Hello", conversation=self.conversation)
        message2 = create_regular_message(
            user=self.user, content="World", conversation=self.conversation)
        message3 = create_regular_message(
            user=self.user, content="Selamta", conversation=self.conversation)

        response = self.get(message2.pk)

        self.conversation.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.conversation.last_message, message3.content)

    def test_non_existing_message_pk(self):
        """
        If the message doesn't exist
        """
        response = self.get(404)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_is_not_creator_of_message(self):
        """
        If the message isn't sent by the logged in user
        """
        message = create_regular_message(
            user=self.participant_user, content="Hello", conversation=self.conversation)

        response = self.get(message.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ReplyMessageApiViewTests(APITestCase):
    def post(self, body):
        url = reverse('api:chat:reply_message', kwargs={'version': 'v1'})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """Non authenticated user should be responded with not authorized response."""
        self.client.logout()
        response = self.post(None)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_replying_to_a_regular_message(self):
        """A successful attempt to make a reply to a regular message should result in 2xx response"""
        conversation = Conversation.objects.create()
        regular_message = RegularMessage.objects.create(
            conversation=conversation)
        response = self.post({'reply_to': regular_message.pk,
                              'reply_type': MessageType.REGULAR_MESSAGE.value})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['reply_to_regular_message_id'], regular_message.id)
        self.assertEqual(response.data['user_id'], self.user.id)
        self.assertTrue(response.data['is_reply'])
        self.assertTrue(response.data['conversation'], conversation.id)

    def test_replying_to_an_invitation_message(self):
        """A successful attempt to make a reply to an invitation message should result in 2xx response"""
        conversation = Conversation.objects.create()
        invitation_message = InvitationMessage.objects.create(
            conversation=conversation)
        response = self.post({'reply_to': invitation_message.pk,
                              'reply_type': MessageType.INVITATION_MESSAGE.value})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['reply_to_invitation_message_id'], invitation_message.id)
        self.assertEqual(response.data['user_id'], self.user.id)
        self.assertTrue(response.data['is_reply'])
        self.assertTrue(response.data['conversation'], conversation.id)

    def test_replying_to_a_mini_suggestion_message(self):
        """A successful attempt to make a reply to a mini suggestion message should result in 2xx response"""
        conversation = Conversation.objects.create()
        mini_suggestion_message = MiniSuggestionMessage.objects.create(
            conversation=conversation)
        response = self.post({'reply_to': mini_suggestion_message.pk,
                              'reply_type': MessageType.MINI_SUGGESTION_MESSAGE.value})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['reply_to_mini_suggestion_message_id'], mini_suggestion_message.id)
        self.assertEqual(response.data['user_id'], self.user.id)
        self.assertTrue(response.data['is_reply'])
        self.assertTrue(response.data['conversation'], conversation.id)

    def test_replying_without_sending_the_reply_to_message(self):
        """It should respond with a bad request if the reply_to, or reply_type is omitted in the request"""
        mini_suggestion_message = MiniSuggestionMessage.objects.create()
        response = self.post(
            {'reply_type': MessageType.MINI_SUGGESTION_MESSAGE.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.post({'reply_to': mini_suggestion_message.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ForwardMessageApiViewTests(APITestCase):
    def post(self, message_id, body):
        url = reverse('api:chat:forward_message', kwargs={'version': 'v1',
                                                          'pk': message_id})
        return self.client.post(url, body)

    def setUp(self) -> None:
        conversation = Conversation.objects.create()
        self.user = create_user_and_login(self)
        conversation.add_participant(
            self.user, Participant.ROLES.MOOGTER.value)
        self.message = create_regular_message(
            self.user, 'test content', conversation)

    def test_non_authorized(self):
        """Non authorized user should get a non authorized response."""
        self.client.logout()
        response = self.post(self.message.id, None)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_message(self):
        """A message that doesn't exist can't be forwarded hence a 404 error."""
        response = self.post(404, None)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_existing_recipient(self):
        """If the recipient of the message doesn't exist, it should respond with a 404 response."""
        response = self.post(self.message.id, {'forwarded_to': 404})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_forward_to_someone_with_conversation_created(self):
        """If you're forwarding to someone you haven't talked to before a new conversation should be created."""
        user = create_user('test_user', 'password')
        response = self.post(self.message.id, {'forward_to': user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RegularMessage.objects.count(), 2)
        self.assertIsNotNone(response.data['forwarded_from_id'])
        self.assertEqual(response.data['forwarded_from_id'], self.user.id)
        self.assertIsNotNone(response.data['conversation'])
        self.assertNotEqual(self.message.conversation_id,
                            response.data['conversation'])

    def test_forward_to_someone_conversation_not_created(self):
        """If you're forwarding to someone you have talked to before a new conversation shouldn't be created."""
        user = create_user('test_user', 'password')
        conversation = Conversation.objects.create()
        conversation.add_participant(user, Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            self.user, Participant.ROLES.MOOGTER.value)
        response = self.post(self.message.id, {'forward_to': user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RegularMessage.objects.count(), 2)
        self.assertIsNotNone(response.data['forwarded_from_id'])
        self.assertEqual(response.data['forwarded_from_id'], self.user.id)
        self.assertIsNotNone(response.data['conversation'])
        self.assertEqual(conversation.id, response.data['conversation'])

    def test_forward_to_someone_new_message_should_have_different_created_at_date(self):
        """The new message that's created after forwarding, should have a different created_at date."""
        user = create_user('test_user', 'password')
        response = self.post(self.message.id, {'forward_to': user.id})
        forwarded_message = RegularMessage.objects.get(pk=response.data['id'])
        self.assertNotEqual(self.message.created_at,
                            forwarded_message.created_at)
        self.assertGreater(forwarded_message.created_at,
                           self.message.created_at)
        self.assertEqual(self.message.content, forwarded_message.content)


class GetMoogtInvitationMessageApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt()
        self.invitation = create_invitation(self.moogt)
        conversation = Conversation.objects.create()
        self.invitation_message = InvitationMessage.objects.create(invitation=self.invitation,
                                                                   conversation=conversation)

    def get(self, moogt_id):
        url = reverse('api:chat:get_moogt_invitation_message', kwargs={'version': 'v1',
                                                                       'pk': moogt_id})
        return self.client.get(url)

    def test_non_authenticated_user(self):
        """
        A non authenticated user should get a non-authorized response.
        """
        self.client.logout()
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """
        Should get a not found response for a moogt that doesn't exist.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_should_return_invitation_message_for_that_moogt(self):
        """
        Should get the invitation message for the particular moogt.
        """
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pk'], self.invitation_message.id)

    def test_should_get_not_found_response_if_invitation_message_does_not_exist(self):
        """
        Should get a not found response for a an invitation message that doesn not exist
        """
        self.invitation_message.delete()
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GetInvitationMessageApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        conversation = Conversation.objects.create()
        conversation.add_participant(
            self.user, Participant.ROLES.MOOGTER.value)
        self.invitation_message = InvitationMessage.objects.create(
            conversation=conversation)

    def get(self, message_id):
        url = reverse('api:chat:get_invitation_message', kwargs={'version': 'v1',
                                                                 'pk': message_id})

        return self.client.get(url)

    def test_non_authenticated_user(self):
        """A non authenticated user cannot get a message detail and thus should get a non-authorized response."""
        self.client.logout()
        response = self.get(self.invitation_message.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_an_invitation_message_successfully(self):
        """If the invitation message exists, it should be returned with a 2xx response."""
        response = self.get(self.invitation_message.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pk'], self.invitation_message.id)

    def test_get_an_invitation_message_which_you_are_not_part_of(self):
        """
        A non participant of the message is not allowed to get the message. Thus should
        get a forbidden response.
        """
        create_user_and_login(self, 'non_participant', 'pass123')
        response = self.get(self.invitation_message.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GetMiniSuggestionMessageApiViewTest(APITestCase):
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        conversation = Conversation.objects.create()
        conversation.add_participant(
            self.user, Participant.ROLES.MOOGTER.value)
        self.mini_suggestion_message = MiniSuggestionMessage.objects.create(
            conversation=conversation)

    def get(self, message_id):
        url = reverse('api:chat:get_mini_suggestion_message', kwargs={'version': 'v1',
                                                                      'pk': message_id})

        return self.client.get(url)

    def test_non_authenticated_user(self):
        """A non authenticated user cannot get a message detail and thus should get a non-authorized response."""
        self.client.logout()
        response = self.get(self.mini_suggestion_message.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_an_invitation_message_successfully(self):
        """If the invitation message exists, it should be returned with a 2xx response."""
        response = self.get(self.mini_suggestion_message.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pk'], self.mini_suggestion_message.id)

    def test_get_an_invitation_message_which_you_are_not_part_of(self):
        """
        A non participant of the message is not allowed to get the message. Thus should
        get a forbidden response.
        """
        create_user_and_login(self, 'non_participant', 'pass123')
        response = self.get(self.mini_suggestion_message.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CountUnreadConversationsApiViewTest(APITestCase):
    """Tests the number of unread conversations, Priority and General conversations"""

    def get(self):
        url = reverse('api:chat:unread_conversation_count',
                      kwargs={'version': 'v1'})
        return self.client.get(url)

    @classmethod
    def setUpTestData(cls):
        cls.conversation: Conversation = Conversation.objects.create()
        cls.participant_user = create_user(
            username='participant_user', password='testpassword')
        cls.conversation.add_participant(
            user=cls.participant_user, role=Participant.ROLES.MOOGTER.value)

        cls.moogt = create_moogt()
        cls.inviter = create_user(
            username='participant_inviter', password='pass123')
        cls.invitee = create_user(
            username='participant_invitee', password='pass123')
        cls.moderator = create_user(
            username='participant_moderator', password='pass123')

        # a conversation should have messages to be shown in priority conversation list
        cls.reg_message = create_regular_message(
            cls.participant_user, "test message", cls.conversation)

        cls.conversation_two: Conversation = Conversation.objects.create()

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.conversation.add_participant(
            user=self.user, role=Participant.ROLES.MOOGTER.value)

    def test_unread_count_priority_conversations(self):
        """check the number of unread conversations in priority conversations including Moderator Invitation Message"""
        self.user.priority_conversations.add(self.conversation)

        moogt = create_moogt('test title')
        invitation = create_invitation(
            moogt=moogt, inviter=moogt.proposition, invitee=moogt.opposition)
        moderator_invitation = create_moderator_invitation(
            invitation=invitation, moderator=self.moderator)
        moderator_invitation.moderator_message.user = self.moderator
        moderator_invitation.moderator_message.conversation = self.conversation
        moderator_invitation.moderator_message.save()

        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['unread_priority_count'], 2)

    def test_unread_count_general_conversations(self):
        """check the number of unread conversations in General conversations"""
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['unread_general_count'], 1)
