from moogts.enums import MoogtWebsocketMessageType
from meda.utils import group_send


async def notify_ws_clients_for_argument(argument, message_type=MoogtWebsocketMessageType.ARGUMENT_CREATED.value):
    """
    Inform clients there is a new argument
    """
    notification = {
        'type': 'receive_group_message',
        'argument_id': argument.id,
        'event_type': message_type
    }

    await group_send(argument.moogt, notification)
