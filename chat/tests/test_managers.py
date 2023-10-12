from django.test import TestCase

from api.tests.utility import create_user, create_regular_message
from chat.models import Conversation, Participant


class ConversationManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_one = create_user(username='user_one', password='pass123')
        cls.user_two = create_user(username='user_two', password='pass123')
        cls.user_three = create_user(username='user_three', password='pass123')

        cls.conversation_one = Conversation.objects.create()
        cls.conversation_two = Conversation.objects.create()

        cls.participant_one = Participant.objects.create(
            user=cls.user_one, conversation=cls.conversation_one)
        cls.participant_two = Participant.objects.create(
            user=cls.user_two, conversation=cls.conversation_one)
        cls.participant_three = Participant.objects.create(
            user=cls.user_two, conversation=cls.conversation_two)

        cls.reg_message = create_regular_message(
            cls.user_one, "test message", cls.conversation_one)
        cls.reg_message_2 = create_regular_message(
            cls.user_two, "test message 2", cls.conversation_two)

    def test_returns_only_own_conversation(self):
        """
        It should only return a user's conversation.
        """
        conversations = Conversation.objects.get_user_conversations(
            self.user_one)
        self.assertEqual(conversations.count(), 1)

        conversations = Conversation.objects.get_user_conversations(
            self.user_two)
        self.assertEqual(conversations.count(), 2)

        conversations = Conversation.objects.get_user_conversations(
            self.user_three)
        self.assertEqual(conversations.count(), 0)

    def test_the_conversation_should_not_include_the_user_as_a_participant(self):
        """
        Current user should not be included in the participants queryset.
        """
        conversations = Conversation.objects.get_user_conversations(
            self.user_one)
        self.assertEqual(conversations.first().participants.count(), 1)

    def test_return_priority_list_conversation(self):
        """
        This tests whether the get_priority_convesations should return a conversation in users priority list
        """
        self.user_one.priority_conversations.add(self.conversation_one)
        conversations = Conversation.objects.get_priority_conversations(
            self.user_one)

        self.assertEqual(conversations.first().id, self.conversation_one.id)

    def test_return_general_list_conversation(self):
        """
        get_general_conversation should return a list of conversation
        """
        self.user_one.priority_conversations.add(self.conversation_one)

        conversation_three: Conversation = Conversation.objects.create()
        Participant.objects.create(
            user=self.user_one, conversation=conversation_three)
        Participant.objects.create(
            user=self.user_three, conversation=conversation_three)
        conversation_three.last_message = "last message"
        conversation_three.save()

        conversations = Conversation.objects.get_general_conversations(
            self.user_one)

        self.assertEqual(conversations.first().id, conversation_three.id)

    # def test_conversation_is_sorted_for_list(self):
    #     """
    #     Conversations should be sorted based on updated it.
    #     """
    #     # conversation_two is updated recently.
    #     self.conversation_one.save()
    #     self.conversation_two.save()
    #     result = Conversation.objects.get_user_conversations(self.user_two)
    #     self.assertEqual(result.first().id, self.conversation_two.id)
    #     self.assertEqual(result.last().id, self.conversation_one.id)

    #     # conversation_one is updated recently.
    #     self.conversation_two.save()
    #     self.conversation_one.save()
    #     result = Conversation.objects.get_user_conversations(self.user_two)
    #     self.assertEqual(result.first().id, self.conversation_one.id)
    #     self.assertEqual(result.last().id, self.conversation_two.id)

    def test_conversations_does_not_show_conversations_which_have_empty_last_message(self):
        """last_message should be not null or not empty"""
        self.conversation_one.last_message = ''
        self.conversation_one.save()
        self.conversation_two.save()
        result = Conversation.objects.get_general_conversations(self.user_two)
        self.assertEqual(result.count(), 1)

        self.user_two.priority_conversations.add(self.conversation_one)
        self.user_two.priority_conversations.add(self.conversation_two)
        result = Conversation.objects.get_priority_conversations(self.user_two)
        self.assertEqual(result.count(), 1)
