from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Count, Q, F, Sum

from users.models import MoogtMedaUser

from .enums import WebSocketMessageType
from .models import MessageSummary, InvitationMessage, MiniSuggestionMessage, ModeratorInvitationMessage, RegularMessage
from notifications.models import Notification, NOTIFICATION_TYPES


def _get_conversation_queryset(participant_one: MoogtMedaUser, participant_two: MoogtMedaUser, exclude_self=True):
    from chat.models import Conversation, Participant

    return Conversation.objects.get_user_conversations(participant_one, exclude_self).filter(
        Q(participants__user=participant_one) &
        Q(participants__role=Participant.ROLES.MOOGTER.value),
    ).filter(
        Q(participants__user=participant_two)
    )


def get_or_create_conversation(inviter, invitee, content=None, exclude_self=True):
    from chat.models import Conversation, Participant

    queryset = _get_conversation_queryset(
        participant_one=inviter, participant_two=invitee, exclude_self=exclude_self)

    if queryset.exists():
        return queryset.first(), False
    else:
        conversation = Conversation.objects.create(last_message=content)
        conversation.add_participant(
            inviter, role=Participant.ROLES.MOOGTER.value)
        conversation.add_participant(
            invitee, role=Participant.ROLES.MOOGTER.value)
        return conversation, True


@transaction.atomic
def create_or_update_conversation(invitation):
    """
    Creates a new conversation if the participants haven't started a conversation
    before or it updates the conversation if it exists.
    """
    from chat.models import InvitationMessage, MessageSummary
    (conversation, created) = get_or_create_conversation(inviter=invitation.get_inviter(),
                                                         invitee=invitation.get_invitee(),
                                                         exclude_self=False)

    try:
        invitation_message = invitation.message
        invitation_message.save()
    except InvitationMessage.DoesNotExist:
        invitation_message = InvitationMessage.objects.create(user=invitation.get_inviter(),
                                                              conversation=conversation,
                                                              invitation=invitation,
                                                              content=f'[Moogt Invite: {invitation.moogt.resolution}]')
        invitation_message.summaries.create(
            actor=invitation.get_inviter(), verb=MessageSummary.VERBS.INVITE.value)


def create_moderator_invitation_message(moderator_invitation):
    from chat.models import ModeratorInvitationMessage
    (conversation, _) = get_or_create_conversation(moderator_invitation.invitation.get_inviter(),
                                                   moderator_invitation.get_moderator(),
                                                   exclude_self=False)

    try:
        moderator_invitation_message = moderator_invitation.moderator_message
        moderator_invitation_message.save()
    except ModeratorInvitationMessage.DoesNotExist:
        moderator_invitation_message = ModeratorInvitationMessage.objects.create(user=moderator_invitation.invitation.get_inviter(),
                                                                                 conversation=conversation,
                                                                                 moderator_invitation=moderator_invitation,
                                                                                 content=f'[Moderator Invite: {moderator_invitation.invitation.moogt.resolution}]',)

        moderator_invitation_message.summaries.create(
            actor=moderator_invitation.invitation.get_inviter(), verb=MessageSummary.VERBS.MODERATE.value)


def create_mini_suggestion_message(mini_suggestion, suggester, suggested=None):
    """
    Creates a new message with the mini suggestion that is passed
    """
    from chat.models import MiniSuggestionMessage

    invitation = mini_suggestion.moogt.invitations.first()
    inviter = None
    invitee = None
    if invitation:
        inviter = invitation.get_inviter()
        invitee = invitation.get_invitee()
        suggested = invitee if suggester == inviter else inviter

    (conversation, _) = get_or_create_conversation(
        suggester, suggested, exclude_self=False)

    mini_suggestion_message = MiniSuggestionMessage.objects.create(user=suggester,
                                                                   conversation=conversation,
                                                                   mini_suggestion=mini_suggestion,
                                                                   content=suggester.first_name + " made a suggestion",
                                                                   inviter=inviter,
                                                                   invitee=invitee)
    mini_suggestion_message.summaries.create(
        actor=suggester, verb=MessageSummary.VERBS.SUGGEST.value)


def serialize_message(message):
    from chat.serializers import MessageSerializer

    serializer = MessageSerializer(
        {
            'pk': message.id,
            'when': message.created_at,
            'conversation': message.conversation.id,
            'object': message
        },
    )

    return serializer.data


def serialize_conversation(conversation):
    from chat.serializers import ConversationSerializer

    serializer = ConversationSerializer(conversation)

    return serializer.data


def notify_ws_clients(conversation, message, message_type=WebSocketMessageType.MESSAGE.value):
    """
    Inform clients there is a new message.
    """
    notification = None
    if message_type == WebSocketMessageType.MESSAGE.value:
        serialized_message = serialize_message(message)

        notification = {
            'type': 'receive_group_message',
            'message': serialized_message,
            'message_type': message_type
        }
    elif message_type == WebSocketMessageType.CONVERSATION_UPDATED.value:
        serialized_conversation = serialize_conversation(conversation)

        notification = {
            'type': 'receive_group_message',
            'conversation': serialized_conversation,
            'message_type': message_type
        }

    elif message_type == WebSocketMessageType.SUMMARY_CREATED.value:
        from .serializers import MessageSummarySerializer

        notification = {
            'type': 'receive_group_message',
            'summary': MessageSummarySerializer(message).data,
            'message_type': message_type
        }

    group_send(conversation, notification)


def notify_message_read(conversation, date):
    message = {
        'type': 'receive_group_message',
        'conversation': serialize_conversation(conversation),
        'date': date,
        'message_type': WebSocketMessageType.MESSAGE_READ.value
    }
    group_send(conversation, message)


def group_send(conversation, notification):
    channel_layer = get_channel_layer()
    if conversation:
        for participant in conversation.participants.all():
            async_to_sync(channel_layer.group_send)(
                f'{participant.user.id}', notification)


def get_notification_message_type(message):
    if isinstance(message, InvitationMessage):
        return NOTIFICATION_TYPES.invitation_sent
    elif isinstance(message, RegularMessage):
        return NOTIFICATION_TYPES.regular_message
    elif isinstance(message, MiniSuggestionMessage):
        return NOTIFICATION_TYPES.mini_suggestion_new
    elif isinstance(message, ModeratorInvitationMessage):
        return NOTIFICATION_TYPES.moderator_request


def lock_conversation(participant_one, participant_two):
    _lock_unlock_conversation(participant_one, participant_two, True)


def unlock_conversation(participant_one, participant_two):
    _lock_unlock_conversation(participant_one, participant_two, False)


def _lock_unlock_conversation(participant_one, participant_two, is_locked):
    conversation_queryset = _get_conversation_queryset(
        participant_one, participant_two)
    if conversation_queryset.exists():
        conversation = conversation_queryset.first()
        conversation.is_locked = is_locked
        conversation.save()


def unread_messages(user):
    from .models import Conversation

    unread_messages_count = Conversation.objects.get_user_conversations(
        user=user).aggregate(Sum('unread_messages_count'))['unread_messages_count__sum']

    return unread_messages_count
