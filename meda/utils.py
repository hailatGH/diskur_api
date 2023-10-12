from channels.layers import get_channel_layer


async def group_send(moogt, notification):
    channel_layer = get_channel_layer()
    if moogt:
        await channel_layer.group_send(f'{moogt.id}', notification)
