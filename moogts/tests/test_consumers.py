import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from api.tests.utility import create_moogt_with_user
from arguments.enums import ArgumentActivityType
from arguments.models import Argument, ArgumentActivity
from chat.tests.test_consumers import create_user
from meda.enums import ActivityStatus
from moogtmeda.routing import application
from moogts.enums import MoogtActivityType, MoogtWebsocketMessageType, MOOGT_WEBSOCKET_EVENT
from moogts.models import MoogtActivity, Donation


async def create_argument(user, moogt, content):
    return await database_sync_to_async(Argument.objects.create)(moogt=moogt, user=user, argument=content)


async def create_argument_activity(user, argument, type, status):
    return await database_sync_to_async(ArgumentActivity.objects.create)(argument=argument, type=type, status=status,
                                                                         user=user)


async def update_activity(activity, status):
    activity.status = status
    return await database_sync_to_async(activity.save)()


async def delete_argument(argument):
    return await database_sync_to_async(argument.delete)()


async def create_moogt_activity(user, moogt, type, status):
    return await database_sync_to_async(MoogtActivity.objects.create)(moogt=moogt,
                                                                      type=type,
                                                                      user=user,
                                                                      status=status)


async def create_donation(user, moogt):
    return await database_sync_to_async(Donation.objects.create)(moogt=moogt,
                                                                 user=user)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestConsumer:
    async def test_anonymous_user_should_not_connect(self):
        communicator = WebsocketCommunicator(
            application=application,
            path='/ws/moogt/1/'
        )
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async def test_user_with_invalid_token_should_not_connect(self):
        communicator = WebsocketCommunicator(
            application=application,
            path='/ws/moogt/1/?token=invalid_token'
        )
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    async def test_user_should_connect(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )

        moogt = create_moogt_with_user(proposition_user=user)

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    async def test_broadcasts_a_message_when_an_argument_activity_is_created(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        moogt = create_moogt_with_user(proposition_user=user)

        argument = await create_argument(user, moogt, 'test content')

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()
        activity = await create_argument_activity(user, argument, ArgumentActivityType.EDIT.value,
                                                  ActivityStatus.PENDING.value)

        response = await communicator.receive_json_from()

        argument.refresh_from_db()

        assert response['argument_id'] is argument.id
        assert argument.activities.first().id is activity.id
        assert response['event_type'] == MoogtWebsocketMessageType.ARGUMENT_UPDATED.value
        await communicator.disconnect()

    async def test_broadcasts_a_message_when_a_moogt_activity_is_created(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        moogt = create_moogt_with_user(proposition_user=user)
        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()

        activity = await create_moogt_activity(user, moogt, MoogtActivityType.CARD_REQUEST.name,
                                               ActivityStatus.PENDING.name)
        response = await communicator.receive_json_from()

        moogt.refresh_from_db()

        assert response['moogt_id'] is moogt.id
        assert response['event_type'] == MoogtWebsocketMessageType.MOOGT_UPDATED.value
        assert moogt.activities.first().id is activity.id
        await communicator.disconnect()

    async def test_broadcasts_a_message_when_a_moogt_activity_is_updated(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        moogt = create_moogt_with_user(proposition_user=user)
        activity = await create_moogt_activity(user, moogt, MoogtActivityType.CARD_REQUEST.name,
                                               ActivityStatus.PENDING.name)

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()

        await update_activity(activity, ActivityStatus.ACCEPTED.value)
        response = await communicator.receive_json_from()
        assert response['moogt_id'] is moogt.id
        assert moogt.activities.first().id is activity.id
        await communicator.disconnect()

    async def test_sends_a_message_when_a_donation_is_made(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        moogt = create_moogt_with_user(proposition_user=user)

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()

        donation = await create_donation(user, moogt)

        response = await communicator.receive_json_from()
        assert response['donation']['id'] is donation.id
        assert response['event_type'] == MoogtWebsocketMessageType.DONATION_MADE.name

    async def test_receive_is_typing_event_from_clients(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )

        moogt = create_moogt_with_user(proposition_user=user)

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()

        await communicator.send_json_to({'type': MOOGT_WEBSOCKET_EVENT.start_is_typing})

        response = await communicator.receive_json_from()
        assert response is not None
        assert response['user_id'] is user.id
        assert response['event_type'] == MOOGT_WEBSOCKET_EVENT.user_is_typing

    async def test_receive_is_typing_event_from_non_moogter(self):
        moogter, _ = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        user, access = await create_user(
            'nonmoogter.user@example.com', 'pAssw0rd'
        )
        moogt = create_moogt_with_user(proposition_user=moogter)

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()

        await communicator.send_json_to({'type': MOOGT_WEBSOCKET_EVENT.start_is_typing})
        assert await communicator.receive_nothing() is True

    async def test_receive_is_typing_event_is_sent_to_others(self):
        moogter, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )
        opposition, opposition_access = await create_user('oppo@example.com', 'pAssw0rd')

        moogt = create_moogt_with_user(proposition_user=moogter)

        prop_communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        opp_communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={opposition_access}'
        )
        connected, _ = await prop_communicator.connect()
        connected, _ = await opp_communicator.connect()

        await prop_communicator.send_json_to({'type': MOOGT_WEBSOCKET_EVENT.start_is_typing})
        response = await opp_communicator.receive_json_from()
        assert response is not None
        assert response['user_id'] is moogter.id
        assert response['event_type'] == MOOGT_WEBSOCKET_EVENT.user_is_typing

    async def test_make_sure_is_typing_event_is_received_from_in_turn_user(self):
        user, access = await create_user(
            'test.user@example.com', 'pAssw0rd'
        )

        moogt = create_moogt_with_user(proposition_user=user, started_at_days_ago=1)
        moogt.next_turn_proposition = False
        moogt.save()

        communicator = WebsocketCommunicator(
            application=application,
            path=f'/ws/moogt/{moogt.id}/?token={access}'
        )
        connected, _ = await communicator.connect()

        await communicator.send_json_to({'type': MOOGT_WEBSOCKET_EVENT.start_is_typing})

        assert await communicator.receive_nothing() is True
