from channels.db import database_sync_to_async
from channels.exceptions import StopConsumer
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.shortcuts import get_object_or_404

from .enums import MOOGT_WEBSOCKET_EVENT
from .models import Moogt


class MoogtDetailConsumer(AsyncJsonWebsocketConsumer):
    """
    This Moogt Detail consumer handles websocket connections for moogt clients.

    It uses AsyncWebsocketConsumer, which means all the handling functions
    must be async functions, and any sync work (like ORM access) has to be
    behind database_sync_to_async or sync_to_async. For more, read
    http://channels.readthedocs.io/en/latest/topics/consumers.html
    """

    async def connect(self):
        """
        Called when the websocket is handshaking as part of initial connection.
        """
        moogt_id = self.scope["url_route"]["kwargs"]["pk"]

        user = self.scope['user']
        # Are they logged in?
        if user.is_anonymous:
            # Reject the connection
            await self.close()
        else:
            moogt = await database_sync_to_async(get_object_or_404)(Moogt, pk=moogt_id)
            self.group_name = f'{moogt.id}'
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
        if content.get('type') == MOOGT_WEBSOCKET_EVENT.start_is_typing:
            user = self.scope['user']
            moogt: Moogt = await database_sync_to_async(get_object_or_404)(Moogt, pk=self.group_name)
            if moogt.func_is_participant(user) and moogt.func_is_current_turn(user):
                await self.channel_layer.group_send(self.group_name,
                                                    {'type': 'receive_group_message',
                                                     'user_id': user.id,
                                                     'event_type': MOOGT_WEBSOCKET_EVENT.user_is_typing})

    async def receive_group_message(self, event):
        # Remove the type key
        # event.pop('type', None)

        # Send message to WebSocket
        await self.send_json(content=event)

    def serialize_argument(self, argument):
        from arguments.serializers import ArgumentSerializer
        serializer = ArgumentSerializer(argument, context={"request": SimpleRequest(self.scope['user']),
                                                           'expand': {'reply_to', 'activities', 'modified_child',
                                                                      'images', 'react_to'}})
        return serializer.data

    def serializer_moogt(self, moogt):
        from moogts.serializers import MoogtSerializer
        serializer = MoogtSerializer(moogt, context={"request": SimpleRequest(self.scope['user']),
                                                     "expand": {'tags', 'banner', 'activities'}})

        return serializer.data


class SimpleRequest:
    def __init__(self, user):
        self.user = user
