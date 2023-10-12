from django.db import models
from django.db.models import Prefetch, Q, Count, F
from django.db.models.functions import Length
from model_utils.managers import SoftDeletableManager


class ConversationManager(models.Manager):

    def get_user_conversations(self, user, exclude_self=True):
        from chat.models import Participant

        if exclude_self:
            prefetched_participants = Prefetch(
                'participants', queryset=Participant.objects.exclude(user=user))
        else:
            prefetched_participants = Prefetch('participants')

        return self.get_queryset().annotate(last_message_len=Length('last_message'),
                                            unread_regular=Count('regular_messages', filter=Q(
                                                Q(regular_messages__is_read=False) & ~Q(regular_messages__user=user)), distinct=True),
                                            unread_invitation=Count('invitation_messages', filter=Q(
                                                Q(invitation_messages__is_read=False) & ~Q(invitation_messages__user=user)), distinct=True),
                                            unread_minisuggestion=Count('mini_suggestion_messages', filter=Q(
                                                Q(mini_suggestion_messages__is_read=False) & ~Q(mini_suggestion_messages__user=user)), distinct=True),
                                            unread_moderator_invitation_message=Count('moderator_invitation_messages', filter=Q(
                                                Q(moderator_invitation_messages__is_read=False) & ~Q(moderator_invitation_messages__user=user)), distinct=True),
                                            unread_messages_count=F('unread_regular') + F('unread_invitation') + F('unread_minisuggestion') + F('unread_moderator_invitation_message'),).prefetch_related(
            prefetched_participants,
        ).filter(participants__user=user).order_by('-updated_at')

    def get_priority_conversations(self, user):
        return self.get_user_conversations(user).filter(
            Q(prioritizers=user), last_message__isnull=False, last_message_len__gt=0).distinct()

    def get_general_conversations(self, user):
        return self.get_user_conversations(user).filter(
            ~Q(prioritizers=user), last_message__isnull=False, last_message_len__gt=0).distinct()

    def get_recent_user_conversations(self, user):
        return self.get_user_conversations(user=user)[:5]


class MessageManager(SoftDeletableManager):
    def get_queryset(self):
        return super().get_queryset().select_related('user', 'user__profile')


class MessageSummaryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('actor', 'actor__profile')


class RegularMessageManager(MessageManager):
    def get_queryset(self):
        return super().get_queryset().select_related('forwarded_from', 'forwarded_from__profile')


class InvitationMessageManager(MessageManager):
    def get_queryset(self):
        return super().get_queryset().select_related('invitation',
                                                     'invitation__inviter',
                                                     'invitation__inviter__profile',
                                                     'invitation__invitee',
                                                     'invitation__invitee__profile',
                                                     'invitation__moderator_invitation__moderator',
                                                     'invitation__moderator_invitation__moderator__profile')


class ModeratorInvitationMessageManager(MessageManager):
    def get_queryset(self):
        return super().get_queryset().select_related('moderator_invitation',
                                                     'moderator_invitation__moderator',
                                                     'moderator_invitation__moderator__profile',
                                                     'moderator_invitation__invitation',
                                                     'moderator_invitation__invitation__inviter',
                                                     'moderator_invitation__invitation__inviter__profile',
                                                     'moderator_invitation__invitation__invitee',
                                                     'moderator_invitation__invitation__invitee__profile')
