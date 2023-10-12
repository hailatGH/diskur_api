from django.db.models.functions import Length
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseForbidden, Http404
from rest_framework import status, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, CreateAPIView, RetrieveAPIView, get_object_or_404, GenericAPIView
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin

from api.pagination import SmallResultsSetPagination
from api.utils import get_union_queryset, inflate_referenced_objects
from chat.enums import ConversationType, MessageType
from chat.models import Conversation, RegularMessage, InvitationMessage, MiniSuggestionMessage
from chat.serializers import ConversationSerializer, MessageSerializer, \
    RegularMessageSerializer
from chat.utils import get_or_create_conversation, notify_message_read
from chat.serializers import UnreadConversationCountSerializer
from moogts.models import Moogt
from users.models import MoogtMedaUser

from django.db.models import Sum


class ListConversationApiView(SerializerExtensionsAPIViewMixin, ListAPIView):
    """
    Get a list of conversation messages for a particular user.
    """
    serializer_class = ConversationSerializer

    def get_queryset(self):
        user = self.request.user

        list_type = self.request.query_params.get(
            'type', ConversationType.GENERAL.value)
        if list_type == ConversationType.PRIORITY.value:
            return Conversation.objects.get_priority_conversations(user=user)
        elif list_type == ConversationType.GENERAL.value:
            return Conversation.objects.get_general_conversations(user=user)
        else:
            return Conversation.objects.get_user_conversations(user=user)


class RecentConversationsApiView(SerializerExtensionsAPIViewMixin, ListAPIView):
    """
    Get a list of recent conversation messages for a particular user.
    """
    serializer_class = ConversationSerializer

    def get_queryset(self):
        user = self.request.user

        return Conversation.objects.get_recent_user_conversations(user=user)


class PrioritizeConversationApiView(GenericAPIView):
    serializer_class = ConversationSerializer

    def get(self, request, *args, **kwargs):
        conversation_id = self.kwargs.get('pk')
        conversation = get_object_or_404(Conversation, pk=conversation_id)

        if conversation.participants.filter(user=request.user).exists():
            request.user.priority_conversations.add(conversation)

            return Response(self.get_serializer(conversation).data, status=status.HTTP_200_OK)
        else:
            return HttpResponseForbidden()


class UnPrioritizeConversationApiView(GenericAPIView):
    serializer_class = ConversationSerializer

    def get(self, request, *args, **kwargs):
        conversation_id = self.kwargs.get('pk')
        conversation = get_object_or_404(Conversation, pk=conversation_id)

        if conversation.participants.filter(user=request.user).exists():
            if request.user.priority_conversations.filter(id=conversation.id).exists():
                request.user.priority_conversations.remove(conversation)

                return Response(self.get_serializer(conversation).data, status=status.HTTP_200_OK)
            else:
                raise ValidationError('Conversation not prioritized.')
        else:
            return HttpResponseForbidden()


class SendRegularMessageApiView(SerializerExtensionsAPIViewMixin,
                                CreateAPIView):
    serializer_class = RegularMessageSerializer

    def post(self, request, *args, **kwargs):
        if request.data.get('conversation') is None:
            participant_user = get_object_or_404(
                MoogtMedaUser, pk=request.data.get('to'))
            (conversation, _) = get_or_create_conversation(participant_user, request.user,
                                                           content=request.data['content'])
            request.data['conversation'] = conversation.id
        else:
            conversation = get_object_or_404(
                Conversation, pk=request.data.get('conversation'))

        if conversation.is_locked:
            raise PermissionDenied(
                'You cannot send messages in a locked conversation.')

        return super().post(request, *args, **kwargs)


class ListMessageApiView(ListAPIView):
    """
    Get a list of messages in a particular conversation.
    """
    serializer_class = MessageSerializer
    pagination_class = SmallResultsSetPagination
    querysets = {}

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            page = inflate_referenced_objects(
                union_qs=page, **self.querysets, field_to_include='conversation')
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        queryset = inflate_referenced_objects(
            union_qs=queryset, **self.querysets, field_to_include='conversation')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        conversation = get_object_or_404(
            Conversation, pk=self.kwargs.get('pk'))
        if not conversation.participants.filter(user=self.request.user).exists():
            raise PermissionDenied()

        self.querysets['invitation_message'] = conversation.invitation_messages.select_related(
            'invitation',
            'invitation__moogt',
            'invitation__moogt__banner').all()

        self.querysets['regular_message'] = conversation.regular_messages.select_related(
            'reply_to_regular_message',
            'reply_to_invitation_message',
            'reply_to_mini_suggestion_message'
        ).all()
        self.querysets['minisuggestion_message'] = conversation.mini_suggestion_messages.all()

        self.querysets['moderator_invitation_message'] = conversation.moderator_invitation_messages.select_related(
            'moderator_invitation',
            'moderator_invitation__invitation',
            'moderator_invitation__invitation__moogt',
        ).all()

        recent = get_union_queryset('conversation',
                                    **self.querysets,
                                    datetime_field='created_at')

        return recent


class MessageDetailApiView(RetrieveAPIView):
    serializer_class = MessageSerializer

    def get_message_object(self, message):
        return {
            'pk': message.id,
            'when': message.created_at,
            'object': message,
            'conversation': message.conversation_id
        }

    def filter_message_queryset(self, queryset):
        return queryset.filter(conversation__participants__user=self.request.user)

    def get_object(self):
        obj = super().get_object()
        return self.get_message_object(obj)


class ReadMessageApiView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.data.get('conversation', None) is None:
            raise ValidationError("conversation field can't be empty")
        elif request.data.get('read_before_date', None) is None:
            raise ValidationError("read_before_date field can't be empty")

        conversation = get_object_or_404(
            Conversation, pk=request.data.get('conversation'))

        # TODO: Deal with this redundancy, i.e., the update logic is repeated three times.
        regular_message_queryset = conversation.regular_messages.exclude(
            user=request.user
        ).filter(
            created_at__lte=request.data['read_before_date'],
            is_read=False,
        )

        invitation_message_queryset = conversation.invitation_messages.exclude(
            user=request.user
        ).filter(
            created_at__lte=request.data['read_before_date'],
            is_read=False,
        )

        mini_suggestion_message_queryset = conversation.mini_suggestion_messages.exclude(
            user=request.user
        ).filter(
            created_at__lte=request.data['read_before_date'],
            is_read=False,
        )

        moderator_invitation_message_queryset = conversation.moderator_invitation_messages.exclude(
            user=request.user
        ).filter(
            created_at__lte=request.data['read_before_date'],
            is_read=False,
        )

        regular_message_queryset.update(is_read=True)
        invitation_message_queryset.update(is_read=True)
        mini_suggestion_message_queryset.update(is_read=True)
        moderator_invitation_message_queryset.update(is_read=True)

        # Notify clients using web socket event here.
        notify_message_read(conversation, request.data['read_before_date'])

        request.user.notifications.mark_notifications_as_read(
            ContentType.objects.get_for_model(Conversation), conversation.id, request.data['read_before_date'])

        return Response({"success": True}, status=status.HTTP_200_OK)


class DeleteMessageApiView(GenericAPIView):
    serializer_class = MessageSerializer

    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        message = get_object_or_404(RegularMessage, pk=pk)

        if self.request.user != message.user:
            return HttpResponseForbidden()

        messages = message.conversation.regular_messages.all().order_by('-created_at')

        if messages.first().id == message.id:
            messages = messages.annotate(content_length=Length(
                'content')).filter(content_length__gt=0).exclude(pk=message.pk)
            if messages.count() > 0:
                message.conversation.last_message = messages.first().content

            else:
                message.conversation.last_message = ''

            message.conversation.save()

        message.pk = None
        message.content = ""
        message.save(prevent_sending_signal=True)

        message = get_object_or_404(RegularMessage, pk=pk)
        message.delete()

        return Response({"success": True}, status=status.HTTP_200_OK)


class GetConversationWithSomeone(GenericAPIView):
    serializer_class = ConversationSerializer

    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        user = get_object_or_404(MoogtMedaUser, pk=pk)
        conversation, created = get_or_create_conversation(request.user, user)

        serializer = self.get_serializer(conversation)

        if created:
            conversation = Conversation.objects.get_user_conversations(
                request.user).filter(id=conversation.id).first()
            serializer = self.get_serializer(conversation)
            return Response(data=serializer.data, status=status.HTTP_201_CREATED)

        return Response(data=serializer.data, status=status.HTTP_200_OK)


class ReplyMessageApiView(SerializerExtensionsAPIViewMixin,
                          CreateAPIView):
    serializer_class = RegularMessageSerializer

    def post(self, request, *args, **kwargs):
        if not request.data.get('reply_to') or not request.data.get('reply_type'):
            raise ValidationError()
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        reply_to = self.request.data.get('reply_to')
        reply_type = self.request.data.get('reply_type')
        if reply_type == MessageType.REGULAR_MESSAGE.value:
            message = get_object_or_404(RegularMessage,
                                        pk=reply_to)
            serializer.save(reply_to=message,
                            conversation=message.conversation)
        elif reply_type == MessageType.INVITATION_MESSAGE.value:
            message = get_object_or_404(InvitationMessage,
                                        pk=reply_to)
            serializer.save(reply_to=message,
                            conversation=message.conversation)

        elif reply_type == MessageType.MINI_SUGGESTION_MESSAGE.value:
            message = get_object_or_404(MiniSuggestionMessage,
                                        pk=reply_to)
            serializer.save(reply_to=message,
                            conversation=message.conversation)


class ForwardMessageApiView(SerializerExtensionsAPIViewMixin,
                            GenericAPIView):
    serializer_class = RegularMessageSerializer
    queryset = RegularMessage.objects.all()

    def post(self, request, *args, **kwargs):
        message = self.get_object()
        forward_to = get_object_or_404(
            MoogtMedaUser, pk=request.data.get('forward_to'))

        conversation, _ = get_or_create_conversation(request.user, forward_to)

        message.pk = None
        message.conversation = conversation
        message.forwarded_from = request.user
        message.save()

        return Response(self.get_serializer(message).data, status=status.HTTP_201_CREATED)


class CountPendingMessagesOfConversationApiView(GenericAPIView):
    """
    Get the number of pending messages in a conversation.
    """
    serializer_class = ConversationSerializer

    def get(self, request, *args, **kwargs):
        conversation_id = self.kwargs.get('pk')
        conversation = get_object_or_404(Conversation, pk=conversation_id)

        pending_mini_suggestions = conversation.get_pending_mini_suggestions()
        count = pending_mini_suggestions.count()

        return Response({"count": count, "result": pending_mini_suggestions}, status=status.HTTP_200_OK)


class GetMoogtInvitationMessageApiView(MessageDetailApiView):

    def get_object(self):
        moogt_id = self.kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        invitation_message = InvitationMessage.objects.filter(
            invitation__moogt=moogt).first()
        if invitation_message:
            return self.get_message_object(invitation_message)

        raise Http404


class GetInvitationMessageApiView(MessageDetailApiView):

    def get_queryset(self):
        return self.filter_message_queryset(InvitationMessage.objects.all())


class GetMiniSuggestionMessageApiView(MessageDetailApiView):

    def get_queryset(self):
        return self.filter_message_queryset(MiniSuggestionMessage.objects.all())


class UnreadConversationCountApiView(GenericAPIView):
    serializer_class = UnreadConversationCountSerializer

    def get(self, request, *args, **kwargs):
        unread_priority_conversation_count = Conversation.objects.get_priority_conversations(
            user=request.user).aggregate(Sum('unread_messages_count'))['unread_messages_count__sum']

        unread_general_conversation_count = Conversation.objects.get_general_conversations(
            user=request.user).aggregate(Sum('unread_messages_count'))['unread_messages_count__sum']

        count_unread = {
            'unread_priority_count': unread_priority_conversation_count,
            'unread_general_count': unread_general_conversation_count,
        }

        return Response(self.get_serializer(count_unread).data)
