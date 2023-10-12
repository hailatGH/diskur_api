from channels.exceptions import StopConsumer
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    This chat consumer handles websocket connections for chat clients.

    It uses AsyncWebsocketConsumer, which means all the handling functions
    must be async functions, and any sync work (like ORM access) has to be
    behind database_sync_to_async or sync_to_async. For more, read
    http://channels.readthedocs.io/en/latest/topics/consumers.html
    """

    async def connect(self):
        """
        Called when the websocket is handshaking as part of initial connection.
        """
        user = self.scope['user']
        # Are they logged in?
        if user.is_anonymous:
            # Reject the connection
            await self.close()
        else:
            self.group_name = f'{user.id}'
            await self.channel_layer.group_add(
                group=self.group_name,
                channel=self.channel_name
            )
            # Accept the connection
            await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                group=self.group_name,
                channel=self.channel_name
            )
        raise StopConsumer()

    async def receive_json(self, content, **kwargs):
        pass

    async def receive_group_message(self, event):
        # Remove the type key
        event.pop('type', None)

        # Send message to WebSocket
        await self.send_json(content=event)
