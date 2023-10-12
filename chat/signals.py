from django.db.models.signals import post_save
from django.dispatch import receiver, Signal

from chat.utils import create_or_update_conversation, create_mini_suggestion_message, create_moderator_invitation_message
from chat.utils import notify_ws_clients, get_notification_message_type
from invitations.models import Invitation, ModeratorInvitation
from chat.utils import get_or_create_conversation
from invitations.serializers import ModeratorInvitationNotificationSerializer
from moogts.enums import MiniSuggestionState
from moogts.models import MoogtMiniSuggestion
from .enums import WebSocketMessageType
from notifications.signals import notify
from notifications.models import Notification
from .models import InvitationMessage, MiniSuggestionMessage, Message, ModeratorInvitationMessage, RegularMessage

# Signal that will be dispatched after saving a message, used to notify web socket clients.
post_message_save = Signal()


@receiver(post_save, sender=Invitation)
def moogt_invitation_receiver(sender, **kwargs):
    invitation = kwargs.get('instance')
    if invitation.get_inviter() and invitation.get_invitee():
        create_or_update_conversation(invitation)


@receiver(post_save, sender=ModeratorInvitation)
def moderator_invitation_receiver(sender, **kwargs):
    moderator_invitation = kwargs.get('instance')
    if moderator_invitation.invitation.get_inviter() and moderator_invitation.get_moderator():
        create_moderator_invitation_message(moderator_invitation)


@receiver(post_save, sender=MoogtMiniSuggestion)
def moogt_suggestion_receiver(sender, **kwargs):
    mini_suggestion = kwargs.get('instance')

    suggester = mini_suggestion.user

    if suggester:
        if mini_suggestion.state is MiniSuggestionState.PENDING.value:
            create_mini_suggestion_message(mini_suggestion, suggester)
        else:
            mini_suggestion.message.save()


@receiver(post_message_save)
def notify_clients(sender, **kwargs):
    message = kwargs.get('message')

    if message.conversation:
        notify_ws_clients(message.conversation, message,
                          message_type=WebSocketMessageType.MESSAGE.value)
        if not message.is_removed:
            message.conversation.last_message = message.content
            message.conversation.save()
        notify_ws_clients(message.conversation, None,
                          message_type=WebSocketMessageType.CONVERSATION_UPDATED.value)

        if message.get_recepient() and message.user:
            from invitations.serializers import InvitationNotificationSerializer
            from moogts.serializers import MoogtMiniSuggestionNotificationSerializer

            send_email = False
            send_telegram = False
            verb = ''
            target_object = message
            data = {}
            push_notification_title = None
            push_notification_description = None
            category = Notification.NOTIFICATION_CATEGORY.normal

            if isinstance(message, InvitationMessage):
                send_email = True
                send_telegram = True
                target_object = message.invitation
                verb = 'invited'
                data = {
                    'invitation': InvitationNotificationSerializer(message.invitation).data,
                }
                push_notification_title = 'You received a Moogt Invite!'
                push_notification_description = f'{message.user} invited you to a Moogt, "{message.invitation.moogt}"'

            elif isinstance(message, ModeratorInvitationMessage):
                verb = 'invited'
                send_email = True
                send_telegram = True
                data = {
                    'invitation': InvitationNotificationSerializer(message.moderator_invitation.invitation).data,
                    'moderator_invitation': ModeratorInvitationNotificationSerializer(message.moderator_invitation).data
                }
                target_object = message.moderator_invitation
                push_notification_title = f'{message.user} Invited you to Moderate!'
                push_notification_description = f'{message.user} invited you to moderate the Moogt, "{message.moderator_invitation.invitation.moogt}"'

            elif isinstance(message, MiniSuggestionMessage):
                target_object = message.mini_suggestion
                verb = 'suggested'
                data = {'mini_suggestion': MoogtMiniSuggestionNotificationSerializer(
                    message.mini_suggestion).data}
            elif isinstance(message, RegularMessage):
                target_object = message
                verb = 'sent'
                push_notification_title = 'You have got a new message'
                push_notification_description = f'{message.user} sent you a message'
                category = Notification.NOTIFICATION_CATEGORY.message

            # to make sure the message is newly created
            if not message.updated_at:
                notify.send(recipient=message.get_recepient().user,
                            sender=message.user,
                            verb=verb,
                            send_email=send_email,
                            type=get_notification_message_type(message),
                            category=category,
                            action_object=message.conversation,
                            send_telegram=send_telegram,
                            target=target_object,
                            timestamp=message.created_at,
                            data=data,
                            push_notification_title=push_notification_title,
                            push_notification_description=push_notification_description
                            )
