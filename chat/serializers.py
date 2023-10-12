from rest_framework import serializers
from rest_framework.fields import SerializerMethodField, IntegerField, DateTimeField
from rest_framework.serializers import ModelSerializer, Serializer
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin

from invitations.serializers import InvitationSerializer
from invitations.serializers import ModeratorInvitationSerializer
from moogts.serializers import MoogtMiniSuggestionSerializer, MoogtSerializer
from users.serializers import MoogtMedaUserSerializer
from .enums import MessageType, ConversationType
from .models import ModeratorInvitationMessage, RegularMessage, Conversation, Participant, InvitationMessage, MiniSuggestionMessage, MessageSummary


class MessageSerializer(Serializer):
    pk = IntegerField()
    type = SerializerMethodField()
    when = DateTimeField()
    object = SerializerMethodField()
    conversation = IntegerField()

    def get_object(self, message_obj):
        obj = message_obj.get('object')

        if isinstance(obj, RegularMessage):
            return RegularMessageSerializer(obj, context={**self.context,
                                                          'expand': {
                                                              'reply_to_invitation_message',
                                                              'reply_to_regular_message',
                                                              'reply_to_mini_suggestion_message'}}).data
        elif isinstance(obj, InvitationMessage):
            return InvitationMessageSerializer(obj, context={**self.context,
                                                             'expand': {
                                                                 'summaries',
                                                                 'summaries__actor__profile',
                                                                 'invitation__moogt',
                                                                 'invitation__moogt__banner',
                                                                 'invitation__moderator_invitation'},
                                                             'exclude': {'invitation__moogt__stats',
                                                                         'invitation__moogt__followers_count',
                                                                         'invitation__moogt__is_following',
                                                                         'invitation__moogt__is_moogt_participant',
                                                                         'invitation__moogt__total_donations',
                                                                         'invitation__moogt__your_donations',
                                                                         'invitation__moogt__arguments_count',
                                                                         'invitation__moogt__latest_read_at',
                                                                         'invitation__moogt__next_turn_proposition',
                                                                         'invitation__moogt__share_count',
                                                                         'invitation__moogt__has_ended',
                                                                         'invitation__moogt__unread_cards_count',
                                                                         'invitation__moogt__is_current_turn',
                                                                         'invitation__moogt__next_turn_user_id',
                                                                         'invitation__moogt__quit_by_id',
                                                                         'invitation__moogt__created_at',
                                                                         'invitation__moogt__updated_at',
                                                                         'invitation__moogt__started_at',
                                                                         'invitation__moogt__moogt_clock_seconds',
                                                                         'invitation__moogt__idle_timer_expire_seconds',
                                                                         'invitation__moogt__max_duration',
                                                                         'invitation__moogt__idle_timeout_duration',
                                                                         }}).data
        elif isinstance(obj, MiniSuggestionMessage):
            return MiniSuggestionMessageSerializer(obj, context={**self.context,
                                                                 'expand': {
                                                                     'summaries',
                                                                     'summaries__actor__profile',
                                                                     'mini_suggestion__tags',
                                                                     'mini_suggestion__banner'}}).data

        elif isinstance(obj, ModeratorInvitationMessage):
            return ModeratorInvitationMessageSerializer(obj, context={**self.context,
                                                                      'expand': {
                                                                          'summaries',
                                                                          'summaries__actor__profile',
                                                                          'moderator_invitation',
                                                                          'moderator_invitation__invitation',
                                                                          'moderator_invitation__invitation__moogt',

                                                                      },
                                                                      'exclude': {
                                                                          'moderator_invitation__invitation__moogt__stats',
                                                                          'moderator_invitation__invitation__moogt__your_donations',
                                                                          'moderator_invitation__invitation__moogt__total_donations',
                                                                          'moderator_invitation__invitation__moogt__latest_read_at',
                                                                          'moderator_invitation__invitation__moogt__unread_cards_count',
                                                                          'moderator_invitation__invitation__moogt__is_current_turn',
                                                                      }}).data
        return None

    def get_type(self, message_obj):
        obj = message_obj.get('object')
        if isinstance(obj, RegularMessage):
            return MessageType.REGULAR_MESSAGE.value
        elif isinstance(obj, InvitationMessage):
            return MessageType.INVITATION_MESSAGE.value
        elif isinstance(obj, MiniSuggestionMessage):
            return MessageType.MINI_SUGGESTION_MESSAGE.value
        elif isinstance(obj, ModeratorInvitationMessage):
            return MessageType.MODERATOR_INVITATION_MESSAGE.value
        return None


class MessageSummarySerializer(SerializerExtensionsMixin, ModelSerializer):
    actor=MoogtMedaUserSerializer(read_only=True)
    
    class Meta:
        model = MessageSummary
        fields = ['id', 'verb', 'created_at', 'actor', 'actor_id']
        expandable_fields = dict(
            mini_suggestion_message=dict(
                serializer='chat.serializers.MiniSuggestionMessageSerializer'),
            invitation_message=dict(
                serializer='chat.serializers.InvitationMessageSerializer'),
        )


class MiniSuggestionMessageSerializer(SerializerExtensionsMixin,
                                      ModelSerializer):
    suggested_child_id = SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)
    edited_parent_id = SerializerMethodField()

    class Meta:
        model = MiniSuggestionMessage
        fields = ('id', 'conversation', 'is_read', 'created_at', 'user', 'user_id',
                  'suggested_child_id', 'edited_parent_id')
        expandable_fields = dict(
            summaries=dict(serializer=MessageSummarySerializer, many=True),
            inviter=dict(serializer=MoogtMedaUserSerializer, read_only=True),
            invitee=dict(serializer=MoogtMedaUserSerializer, read_only=True),
            mini_suggestion=dict(
                serializer=MoogtMiniSuggestionSerializer, read_only=True)
        )

    def get_suggested_child_id(self, mini_suggestion_message):
        try:
            return mini_suggestion_message.mini_suggestion.suggested_child.message.id
        except AttributeError:
            pass

    def get_edited_parent_id(self, mini_suggestion_message):
        try:
            return mini_suggestion_message.mini_suggestion.edited_parent.message.id
        except AttributeError:
            pass


class RegularMessageSerializer(SerializerExtensionsMixin,
                               ModelSerializer):
    user = MoogtMedaUserSerializer(read_only=True)
    forwarded_from = MoogtMedaUserSerializer(read_only=True)
    

    class Meta:
        model = RegularMessage
        fields = ('id', 'content', 'conversation', 'forwarded_from', 'forwarded_from_id',
                  'user', 'user_id', 'is_read', 'is_reply', 'created_at')
        expandable_fields = dict(
            reply_to_regular_message=dict(
                serializer='chat.serializers.RegularMessageSerializer'),
            reply_to_invitation_message=dict(
                serializer='chat.serializers.InvitationMessageSerializer'),
            reply_to_mini_suggestion_message=dict(
                serializer='chat.serializers.MiniSuggestionMessageSerializer'),
        )

    def create(self, validated_data):
        # The message being replied to.
        reply_to = validated_data.pop(
            'reply_to') if 'reply_to' in validated_data else None
        validated_data['user'] = self.context['request'].user

        regular_message = RegularMessage.objects.create(**validated_data)
        if reply_to:
            regular_message.reply_to = reply_to
            regular_message.save()
        return regular_message


class InvitationMessageSerializer(SerializerExtensionsMixin,
                                  ModelSerializer):
    invitation = InvitationSerializer()
    message = SerializerMethodField()
    edited_child_id = SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = InvitationMessage
        fields = ('id', 'created_at', 'invitation', 'conversation', 'user', 'user_id',
                  'message', 'is_read', 'edited_child_id')
        expandable_fields = dict(
            summaries=dict(serializer=MessageSummarySerializer, many=True),
            moogt=dict(serializer=MoogtSerializer, read_only=True),
        )

    def get_message(self, invitation_message):
        try:
            return invitation_message.invitation.get_moogt().get_resolution()
        except AttributeError:
            pass

    def get_edited_child_id(self, invitation_message):
        try:
            return invitation_message.invitation.child_invitation.message.id
        except AttributeError:
            pass


class ModeratorInvitationMessageSerializer(SerializerExtensionsMixin, ModelSerializer):
    user = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = ModeratorInvitationMessage
        fields = ('id', 'created_at', 'moderator_invitation',
                  'user', 'user_id', 'conversation', 'is_read', 'content')

        expandable_fields = dict(
            moderator_invitation=dict(
                serializer=ModeratorInvitationSerializer, read_only=True),
            summaries=dict(
                serializer=MessageSummarySerializer, read_only=True, many=True)
        )


class ParticipantSerializer(ModelSerializer):
    user = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = Participant
        fields = ('id', 'role', 'user', 'user_id')


class ConversationSerializer(ModelSerializer):
    participants = ParticipantSerializer(many=True)
    unread_count = SerializerMethodField()
    type = SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ('id', 'created_at', 'updated_at', 'is_locked', 'participants',
                  'last_message', 'unread_count', 'type')

    def get_unread_count(self, conversation):
        return getattr(conversation, 'unread_messages_count', 0)

    def get_type(self, conversation):
        request = self.context.get('request', None)

        if not request:
            return

        if Conversation.objects.get_priority_conversations(request.user).filter(id=conversation.id).exists():
            return ConversationType.PRIORITY.value
        else:
            return ConversationType.GENERAL.value


class UnreadConversationCountSerializer(serializers.Serializer):
    unread_priority_count = serializers.IntegerField(
        read_only=True)
    unread_general_count = serializers.IntegerField(
        read_only=True)
