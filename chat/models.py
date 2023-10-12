from enum import Enum

from django.core.exceptions import ValidationError
from django.db import models
from model_utils.models import SoftDeletableModel

from chat.managers import ConversationManager, MessageManager, MessageSummaryManager, InvitationMessageManager, RegularMessageManager
from invitations.models import Invitation
from meda.behaviors import Timestampable
from invitations.models import ModeratorInvitation
from chat.managers import ModeratorInvitationMessageManager
from moogts.models import MoogtMiniSuggestion
from users.models import MoogtMedaUser


class Conversation(Timestampable):
    """
    A model that represents a conversation between MoogtMedaUsers.
    """

    last_message = models.CharField(max_length=560, null=True)

    is_locked = models.BooleanField(default=False)

    objects = ConversationManager()

    def add_participant(self, user, role):
        participant = Participant(user=user, role=role, conversation=self)
        # This is to validate the role, i.e. based on the choices given to the CharField.
        # If it's invalid it will throw a ValidationError.
        participant.full_clean()
        participant.save()
        self.participants.add(participant)

    def get_pending_mini_suggestions(self):
        from moogts.enums import MiniSuggestionState

        return self.mini_suggestion_messages.filter(
            mini_suggestion__state=MiniSuggestionState.PENDING.value
        ).order_by('-created_at').values_list('id', flat=True)

    def __str__(self):
        return str(self.last_message)


class Participant(models.Model):
    """
    A MoogtMedaUser who is involved in a particular conversation.
    """

    class ROLES(Enum):
        """Represents the role of a particular user in the conversation."""
        MODERATOR = 'mod'
        MOOGTER = 'mog'

        @classmethod
        def all(cls):
            return [(role.value, role.name.capitalize()) for role in cls]

    # The particular conversation that this participant is involved in.
    conversation = models.ForeignKey(Conversation,
                                     on_delete=models.CASCADE,
                                     related_name='participants')

    # The role of the current participant in the conversation.
    role = models.CharField(max_length=3,
                            choices=ROLES.all(),
                            default=ROLES.MOOGTER.value)

    # The MoogtMedaUser object that is in this conversation.
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='+',
                             on_delete=models.SET_NULL,
                             null=True)


class Message(Timestampable, SoftDeletableModel):
    """
    A chat message sent in a conversation.
    """
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='+',
                             on_delete=models.SET_NULL,
                             null=True)

    # The content of this message.
    content = models.CharField(max_length=560, null=True)

    # Whether or not this message has been read or not.
    is_read = models.BooleanField(default=False)

    object = MessageManager()

    class Meta:
        abstract = True

    def dispatch_signal(self):
        if not self.is_removed:
            from chat.signals import post_message_save
            post_message_save.send(__class__, message=self)

    def has_been_read_by(self, user):
        if user == self.user:
            return True
        return self.is_read

    def get_recepient(self):
        return self.conversation.participants.exclude(user=self.user).first()


class InvitationMessage(Message):
    """
    A message that is created when you invite someone to a moogt.
    """
    # The particular conversation where this message belongs.
    conversation = models.ForeignKey(Conversation,
                                     related_name='invitation_messages',
                                     on_delete=models.SET_NULL,
                                     null=True)

    # The invitation that resulted in the creation of this message.
    invitation = models.OneToOneField(Invitation,
                                      related_name='message',
                                      on_delete=models.SET_NULL,
                                      null=True)

    objects = InvitationMessageManager()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.dispatch_signal()


class MiniSuggestionMessage(Message):
    """
    A message that is created when you suggest a change in moogt
    """
    # The particular conversation where this suggestion belongs
    conversation = models.ForeignKey(Conversation,
                                     related_name='mini_suggestion_messages',
                                     on_delete=models.SET_NULL,
                                     null=True)

    # The mini suggestion that resulted in the creation of this message.
    mini_suggestion = models.OneToOneField(MoogtMiniSuggestion,
                                           related_name='message',
                                           on_delete=models.SET_NULL,
                                           null=True)

    inviter = models.ForeignKey(MoogtMedaUser,
                                related_name='+',
                                on_delete=models.SET_NULL,
                                null=True)

    invitee = models.ForeignKey(MoogtMedaUser,
                                related_name='+',
                                on_delete=models.SET_NULL,
                                null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.dispatch_signal()


class RegularMessage(Message):
    """
    A message that is created when someone sends a regular message
    """

    # The particular conversation where this message belongs to.
    conversation = models.ForeignKey(Conversation,
                                     related_name='regular_messages',
                                     on_delete=models.SET_NULL,
                                     null=True)

    # The owner of the original message if this message is forwarded.
    forwarded_from = models.ForeignKey(MoogtMedaUser,
                                       related_name='+',
                                       on_delete=models.SET_NULL,
                                       null=True)

    # Whether or not this message is a reply message or not.
    is_reply = models.BooleanField(default=False)

    # The invitation message being replied.
    reply_to_invitation_message = models.ForeignKey(InvitationMessage,
                                                    related_name='+',
                                                    null=True,
                                                    on_delete=models.SET_NULL)

    # The mini suggestion message being replied.
    reply_to_mini_suggestion_message = models.ForeignKey(MiniSuggestionMessage,
                                                         related_name='+',
                                                         null=True,
                                                         on_delete=models.SET_NULL)

    # The regular message being replied.
    reply_to_regular_message = models.ForeignKey('self',
                                                 related_name='+',
                                                 null=True,
                                                 on_delete=models.SET_NULL)

    objects = RegularMessageManager()

    @property
    def reply_to(self):
        if self.reply_to_regular_message:
            return self.reply_to_regular_message
        elif self.reply_to_invitation_message:
            return self.reply_to_invitation_message
        elif self.reply_to_mini_suggestion_message:
            return self.reply_to_mini_suggestion_message

    @reply_to.setter
    def reply_to(self, value):
        if isinstance(value, RegularMessage):
            self.is_reply = True
            self.reply_to_regular_message = value
        elif isinstance(value, InvitationMessage):
            self.is_reply = True
            self.reply_to_invitation_message = value
        elif isinstance(value, MiniSuggestionMessage):
            self.is_reply = True
            self.reply_to_mini_suggestion_message = value
        else:
            raise ValidationError('Invalid message object.')

    def save(self, *args, **kwargs):
        prevent_sending_signal = kwargs.pop('prevent_sending_signal', False)
        super().save(*args, **kwargs)
        if not prevent_sending_signal:
            self.dispatch_signal()


class ModeratorInvitationMessage(Message):
    """
    A message that is created when you invite someone to be a moderator.
    """
    # The particular conversation where this message belongs.
    conversation = models.ForeignKey(Conversation,
                                     related_name='moderator_invitation_messages',
                                     on_delete=models.SET_NULL,
                                     null=True)

    # The invitation that resulted in the creation of this message.
    moderator_invitation = models.OneToOneField(ModeratorInvitation,
                                                related_name='moderator_message',
                                                on_delete=models.SET_NULL,
                                                null=True)

    objects = ModeratorInvitationMessageManager()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.dispatch_signal()


class MessageSummary(Timestampable):
    """
    A summary that tracks change history for messages.
    """

    class VERBS(Enum):
        """Represents the role of a particular user in the conversation."""
        ACCEPT = 'accept'
        APPROVE = 'approve'
        CANCEL = 'cancel'
        EDIT = 'edit'
        INVITE = 'invite'
        SUGGEST = 'suggest'
        DECLINE = 'decline'
        DISAPPROVED = 'disapprove'
        MODERATE = 'moderate'

    # The user who performed the action.
    actor = models.ForeignKey(MoogtMedaUser,
                              related_name='+',
                              on_delete=models.SET_NULL,
                              null=True)

    # This is used to describe the action.
    verb = models.CharField(max_length=255)

    # The linked mini suggestion message.
    mini_suggestion_message = models.ForeignKey(MiniSuggestionMessage,
                                                related_name='summaries',
                                                on_delete=models.SET_NULL,
                                                null=True)

    # The linked invitation message.
    invitation_message = models.ForeignKey(InvitationMessage,
                                           related_name='summaries',
                                           on_delete=models.SET_NULL,
                                           null=True)

    # The linked moderator invitation message.
    moderator_invitation_message = models.ForeignKey(ModeratorInvitationMessage,
                                                     related_name='summaries',
                                                     on_delete=models.SET_NULL,
                                                     null=True)

    objects = MessageSummaryManager()

    @property
    def message(self):
        if self.mini_suggestion_message:
            return self.mini_suggestion_message
        elif self.invitation_message:
            return self.invitation_message
        elif self.moderator_invitation_message:
            return self.moderator_invitation_message
        else:
            raise ValidationError('The message summary has no linked message.')
