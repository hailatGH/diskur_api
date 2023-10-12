import pytest
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework_jwt.settings import api_settings

from chat.enums import WebSocketMessageType
from chat.models import Conversation, Participant, RegularMessage, InvitationMessage, MiniSuggestionMessage
from chat.utils import notify_ws_clients, notify_message_read
from moogtmeda.routing import application

jwt_payload_handler = api_settings.JWT_PAYLOAD_HANDLER
jwt_encode_handler = api_settings.JWT_ENCODE_HANDLER


@database_sync_to_async
def create_user(username, password):
    user = get_user_model().objects.create_user(
        username=username,
        password=password
    )

    payload = jwt_payload_handler(user)
    access = jwt_encode_handler(payload)

    return user, access


def create_conversation(user):
    conversation = Conversation.objects.create()
    conversation.add_participant(user=user, role=Participant.ROLES.MOOGTER.value)
    return conversation


async def create_regular_message(user, content):
    conversation = await database_sync_to_async(create_conversation)(user)
    return await database_sync_to_async(RegularMessage.objects.create)(conversation=conversation, content=content,
                                                                       user=user)


async def create_invitation_message(user):
    conversation = await database_sync_to_async(create_conversation)(user)
    return await database_sync_to_async(InvitationMessage.objects.create)(user=user, conversation=conversation)


async def create_mini_suggestion_message(user):
    conversation = await database_sync_to_async(create_conversation)(user)
    return await database_sync_to_async(MiniSuggestionMessage.objects.create)(user=user, conversation=conversation)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestConsumer:

    async def test_anonymous_user_should_not_connect(self):
        communicator = WebsocketCommunicator(
            application=application,
            path='/ws/chat/'
        )
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async def test_user_with_invalid_token_should_not_connect(self):
        communicator = WebsocketCommunicator(
            application=application,
            path='/ws/chat/?token=invalid_token'
        )
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async def test_user_should_connect(self):
        _, access = await create_user(  #
            'test.user@example.com', 'pAssw0rd'
        )
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/chat/?token={access}'
        )
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    async def test_broadcasts_a_message_when_a_regular_message_is_created(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/chat/?token={access}'
        )
        connected, _ = await communicator.connect()
        message = await create_regular_message(user, 'test content')
        response = await communicator.receive_json_from()
        assert response['message']['pk'] is message.id
        assert response['message_type'] == WebSocketMessageType.MESSAGE.value
        assert response['message']['type'] == 'regular_message'
        await communicator.disconnect()

    async def test_broadcasts_a_message_when_an_invitation_message_is_created(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/chat/?token={access}'
        )
        connected, _ = await communicator.connect()
        message = await create_invitation_message(user)
        response = await communicator.receive_json_from()
        assert response['message']['pk'] is message.id
        assert response['message_type'] == WebSocketMessageType.MESSAGE.value
        assert response['message']['type'] == 'invitation_message'
        await communicator.disconnect()

    async def test_broadcasts_a_message_when_a_mini_suggestion_message_is_created(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/chat/?token={access}'
        )
        connected, _ = await communicator.connect()
        message = await create_mini_suggestion_message(user)
        response = await communicator.receive_json_from()
        assert response['message']['pk'] is message.id
        assert response['message_type'] == WebSocketMessageType.MESSAGE.value
        assert response['message']['type'] == 'mini_suggestion_message'

        await communicator.disconnect()

    async def test_broadcasts_a_conversation_when_notify_ws_client_is_called(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/chat/?token={access}'
        )
        connected, _ = await communicator.connect()
        conversation = await database_sync_to_async(create_conversation)(user)
        await sync_to_async(notify_ws_clients)(conversation=conversation, message=None,
                                               message_type=WebSocketMessageType.CONVERSATION_UPDATED.value)
        response = await communicator.receive_json_from(timeout=1)

        assert response['conversation']['id'] is conversation.id
        assert response['message_type'] == WebSocketMessageType.CONVERSATION_UPDATED.value

        await communicator.disconnect()

    async def test_broadcasts_a_message_when_notify_read_message_is_called(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/chat/?token={access}'
        )
        connected, _ = await communicator.connect()
        conversation = await database_sync_to_async(create_conversation)(user)
        await sync_to_async(notify_message_read)(conversation=conversation, date='2020-10-29T10:27:14.660Z')
        response = await communicator.receive_json_from(timeout=1)

        assert response['date'] == '2020-10-29T10:27:14.660Z'
        assert response['conversation']['id'] is conversation.id
        assert response['message_type'] == WebSocketMessageType.MESSAGE_READ.value

        await communicator.disconnect()
