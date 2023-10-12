import pytest
from channels.testing import WebsocketCommunicator

from api.tests.utility import create_moogt_with_user
from arguments.utils import notify_ws_clients_for_argument
from chat.tests.test_consumers import create_user
from moogts.enums import MoogtWebsocketMessageType
from moogtmeda.routing import application
from moogts.tests.test_consumers import create_argument


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestConsumer:
    async def test_notify_ws_clients_for_argument(self):
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
        await notify_ws_clients_for_argument(argument)
        response = await communicator.receive_json_from()

        assert response['argument_id'] is argument.id
        assert response['event_type'] == MoogtWebsocketMessageType.ARGUMENT_CREATED.value
        await communicator.disconnect()
