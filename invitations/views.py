import django.core
import rest_framework
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import get_object_or_404, get_list_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin

from api.enums import InvitationType
from api.models import Tag
from api.pagination import SmallResultsSetPagination
from chat.models import MessageSummary
from invitations.models import Invitation
from invitations.serializers import InvitationSerializer, InvitationNotificationSerializer
from meda.enums import InvitationStatus
from invitations.models import ModeratorInvitation
from invitations.serializers import ModeratorInvitationSerializer
from meda.enums import ModeratorInvititaionStatus
from chat.models import Conversation
from invitations.serializers import ModeratorInvitationNotificationSerializer
from moogts.enums import MiniSuggestionState
from moogts.models import Moogt, ReadBy
from moogts.serializers import MoogtNotificationSerializer, MoogtSerializer, MoogtMiniSuggestionSerializer
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from users.models import ActivityType, MoogtMedaUser, Activity
from users.serializers import MoogtMedaUserSerializer
from django.utils import timezone


def update_invitation_notification(invitation):
    invitation_content_type = ContentType.objects.get_for_model(Invitation)
    Notification.objects.filter(
        target_content_type=invitation_content_type,
        target_object_id=invitation.id
    ).update(
        data={
            'data': {'invitation': InvitationNotificationSerializer(invitation).data}}
    )


def update_moderator_invitation_notification(moderator_invitation):
    mod_invitation_content_type = ContentType.objects.get_for_model(
        ModeratorInvitation)
    Notification.objects.filter(
        target_content_type=mod_invitation_content_type,
        target_object_id=moderator_invitation.id
    ).update(
        data={
            'data': {'moderator_invitation': ModeratorInvitationNotificationSerializer(moderator_invitation).data,
                     'invitation': InvitationNotificationSerializer(moderator_invitation.invitation).data}
        }
    )


class InviteMoogterView(SerializerExtensionsAPIViewMixin, generics.CreateAPIView):
    http_method_names = ['post']
    serializer_class = InvitationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        moogt_id = request.data.get('moogt_id')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        invitee_id = request.data.get('invitee_id')
        invitee = get_object_or_404(MoogtMedaUser, pk=invitee_id)

        invitation = Invitation.create(
            request.user, invitee, moogt, commit=False)
        try:
            invitation.validate()
            invitation.save()

            serializer = self.get_serializer(invitation)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except django.core.exceptions.ValidationError as err:
            raise rest_framework.exceptions.ValidationError(err)


class UpdateInvitationView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView, ):
    http_method_names = ['post']
    serializer_class = InvitationSerializer

    def post(self, request, *args, **kwargs):
        invitation_id = kwargs.get('pk', None)
        invitation = get_object_or_404(Invitation, pk=invitation_id)
        other_invitation = None

        try:
            other_invitation  = Invitation.objects.get_queryset().get(Q(moogt_id=invitation.moogt.id) & ~Q(pk=invitation_id))
        except:
            pass
      
        try:
            action = request.data.get('action')
            if action == 'back':
                if request.user not in [invitation.get_invitee(), invitation.get_inviter()]:
                    raise ValidationError('You cannot update this invitation.')
                if invitation.get_status() == InvitationStatus.accepted():
                    invitation.set_status(InvitationStatus.pending())

                if invitation.get_status() == InvitationStatus.revised():
                    invitation.set_status(InvitationStatus.pending())

                invitation.save()
                return Response('Successfully updated the invitation.')

            invitation.validate_invitation_open()

            if action == 'accept':
                invitation.validate_updater_is_invitee(request.user)
                if(other_invitation):
                    if(other_invitation.status == InvitationStatus.accepted_by_one_invitee()):
                        invitation.set_status(
                            InvitationStatus.accepted())
                        other_invitation.set_status(
                            InvitationStatus.accepted())
                        other_invitation.save()

                    else:
                        invitation.set_status(
                            InvitationStatus.accepted_by_one_invitee())
                else:
                    invitation.set_status(InvitationStatus.accepted())
                if(invitation.moogt.opposition == None):
                    invitation.moogt.set_opposition(invitation.get_invitee())
                if(invitation.moogt.premiering_date != None):
                    invitation.moogt.is_premiering = True
                invitation.moogt.save()
                invitation.save()

                if hasattr(invitation, 'moderator_invitation'):
                    invitation.moderator_invitation.save()

                invitation_message = invitation.message
                if invitation_message:
                    invitation_message.summaries.create(actor=invitation.get_invitee(),
                                                        verb=MessageSummary.VERBS.ACCEPT.value)

                invitation.moogt.followers.add(request.user)
                request.user.last_opened_following_moogt = invitation.moogt
                Activity.record_activity(request.user.profile,
                                         ActivityType.follow_moogt.name, invitation.moogt.id)

                self.create_moogt_read_by(invitation.moogt)

                notify.send(
                    recipient=invitation.get_inviter(),
                    sender=request.user,
                    verb='has accepted',
                    target=invitation,
                    action_object=invitation.message.conversation,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.invitation_accept_inviter,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    data={'invitation': InvitationNotificationSerializer(
                        invitation).data},
                    push_notification_title=f'{request.user} Accepted your Moogt Invite!',
                    push_notification_description=f'{request.user} accepted your Moogt Invite, "{invitation.moogt}"'
                )
                notify.send(
                    recipient=invitation.get_invitee(),
                    sender=request.user,
                    verb='have accepted',
                    target=invitation,
                    action_object=invitation.message.conversation,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.invitation_accept_invitee,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    data={'invitation': InvitationNotificationSerializer(
                        invitation).data},
                    push_notification_title='You Accepted a Moogt invite!',
                    push_notification_description=f'You Accepted a Moogt, "{invitation.moogt}"')

                update_invitation_notification(invitation)

                return Response('Successfully accepted an invitation', status=status.HTTP_200_OK)

            if action == 'decline':
                invitation.validate_updater_is_invitee(request.user)
                if(other_invitation):
                    other_invitation.set_status(InvitationStatus.declined())
                    other_invitation.save()
                    other_invitation_message = other_invitation.message
                    other_invitation_message.summaries.create(actor=invitation.get_invitee(),
                                                              verb=MessageSummary.VERBS.DECLINE.value)

                invitation.set_status(InvitationStatus.declined())
                invitation.save()

                if hasattr(invitation, 'moderator_invitation'):
                    invitation.moderator_invitation.save()

                invitation_message = invitation.message
                if invitation_message:
                    invitation_message.summaries.create(actor=invitation.get_invitee(),
                                                        verb=MessageSummary.VERBS.DECLINE.value)

                update_invitation_notification(invitation)

                return Response('Successfully declined an invitation', status=status.HTTP_200_OK)

            if action == 'cancel':
                invitation.validate_updater_is_inviter(request.user)

                if(other_invitation):
                    other_invitation.set_status(InvitationStatus.cancelled())
                    other_invitation.save()
                    other_invitation_message = other_invitation.message
                    other_invitation_message.summaries.create(actor=invitation.get_invitee(),
                                                              verb=MessageSummary.VERBS.CANCEL.value)

                invitation.set_status(InvitationStatus.cancelled())
                invitation.save()

                if hasattr(invitation, 'moderator_invitation'):
                    invitation.moderator_invitation.save()

                invitation_message = invitation.message
                if invitation_message:
                    invitation_message.summaries.create(actor=invitation.get_inviter(),
                                                        verb=MessageSummary.VERBS.CANCEL.value)

                update_invitation_notification(invitation)

                return Response('Successfully cancelled an invitation', status=status.HTTP_200_OK)

            raise rest_framework.exceptions.ValidationError(
                'Invalid attempt to update an invitation.')
        except django.core.exceptions.ValidationError as err:
            raise rest_framework.exceptions.ValidationError(err)

    def create_moogt_read_by(self, moogt):
        queryset = self.request.user.read_moogts.filter(moogt=moogt)
        if not queryset.exists():
            return ReadBy.objects.create(user=self.request.user, moogt=moogt)

        read_by = queryset.first()
        read_by.latest_read_at = timezone.now()
        read_by.save()

        return read_by


class PendingInvitationListView(SerializerExtensionsAPIViewMixin, generics.ListAPIView, ):
    serializer_class = InvitationSerializer
    pagination_class = SmallResultsSetPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        invitation_type = self.request.query_params.get('type', '')
        invitations = Invitation.objects
        if invitation_type == InvitationType.SENT.name:
            invitations = invitations.filter(
                inviter=self.request.user, status=InvitationStatus.PENDING.name)
        elif invitation_type == InvitationType.RECEIVED.name:
            invitations = invitations.filter(
                invitee=self.request.user, status=InvitationStatus.PENDING.name)
        else:
            invitations = invitations.filter(Q(invitee=self.request.user) | Q(inviter=self.request.user),
                                             status=InvitationStatus.PENDING.name)
        return invitations.order_by('-created_at')


class RecentlyInvitedUsersApiView(generics.ListAPIView):
    serializer_class = MoogtMedaUserSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = SmallResultsSetPagination
    ordering = ['-created_at']

    def get_queryset(self):
        invitations = Invitation.objects.distinct().filter(
            inviter=self.request.user)[:5]
        invitee_ids = [invitation.invitee.pk for invitation in invitations]
        invited_users = MoogtMedaUser.objects.filter(pk__in=invitee_ids)
        return invited_users


class EditInvitationView(generics.GenericAPIView):
    serializer_class = MoogtSerializer

    def post(self, request, *args, **kwargs):
        invitation_id = kwargs.get('pk')
        parent_invitation = get_object_or_404(Invitation, pk=invitation_id)

        if request.user != parent_invitation.get_inviter():
            raise PermissionDenied('You cannot edit this invite.')

        changes = self.request.data
        if changes:
            changes = {key: value for (key, value) in changes.items() if value and
                       key in MoogtMiniSuggestionSerializer.allowed_fields}
            if len(changes) > 0:
                moogt = parent_invitation.moogt
                tags = changes.pop('tags') if 'tags' in changes else None
                serializer = self.get_serializer(
                    moogt, data=changes, partial=True)
                if serializer.is_valid(raise_exception=True):
                    new_moogt: Moogt = serializer.save(
                        clone=True, banner=changes.get('banner', None))
                    self.add_tags(tags, new_moogt)
                    self.create_child_invitation(
                        invitation_id, parent_invitation, new_moogt)
                    return Response(status=status.HTTP_201_CREATED)
            else:
                raise rest_framework.exceptions.ValidationError(
                    'You must provide the changes.')
        else:
            raise rest_framework.exceptions.ValidationError(
                'You must provide the changes.')

    def create_child_invitation(self, invitation_id, parent_invitation, moogt):
        parent_invitation.set_status(InvitationStatus.edited())
        parent_invitation.save()
        invitation_message = parent_invitation.message
        if invitation_message:
            invitation_message.summaries.create(verb=MessageSummary.VERBS.EDIT.value,
                                                actor=parent_invitation.get_inviter())

        # Copy the invitation object
        parent_invitation.pk = None
        parent_invitation.message = None
        parent_invitation.set_status(InvitationStatus.pending())
        parent_invitation.parent_invitation_id = invitation_id
        parent_invitation.moogt = moogt
        parent_invitation.save()

    def add_tags(self, tags, moogt):
        if not tags:
            return
        for tag in tags:
            t, _ = Tag.objects.get_or_create(name=tag['name'])
            moogt.tags.add(t)


class StartInvitationView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        invitation_id = kwargs.get('pk')
        invitation: Invitation = get_object_or_404(
            Invitation, pk=invitation_id)

        # Check if there are pending suggestions. If there exists pending suggestion
        # It shouldn't be started.
        pending_suggestions = invitation.moogt.mini_suggestions.filter(
            state=MiniSuggestionState.PENDING.value)
        if invitation.get_status() == InvitationStatus.revised() and pending_suggestions:
            raise ValidationError(
                'An invitation that has pending suggestion cannot be started.')

        action = request.data.get('action')

        if action == 'now':
            if not invitation.get_status() == InvitationStatus.accepted():
                raise ValidationError('This invitation cannot be started now.')

            if request.user not in [invitation.get_inviter(), invitation.get_invitee()]:
                raise ValidationError('You cannot start this invitation now.')

            # invitation.moogt.set_opposition(invitation.get_invitee())
            invitation.moogt.save()
            invitation.set_status(InvitationStatus.started())
            invitation.save()

            if hasattr(invitation, 'moderator_invitation'):
                invitation.moderator_invitation.save()

            invitee = invitation.get_invitee()
            inviter = invitation.get_inviter()
            recipient = MoogtMedaUser.objects.filter(
                Q(id=invitee.id) | Q(id=inviter.id))  # | invitee.followers | inviter.followers

            notify.send(
                recipient=request.user,
                sender=request.user,
                verb='have started',
                target=invitation.moogt,
                type=NOTIFICATION_TYPES.moogt_status,
                send_email=False,
                send_telegram=True,
                data={'moogt': MoogtNotificationSerializer(
                    invitation.moogt).data},
                push_notification_title='Moogt Started!',
                push_notification_description=f'Your Moogt with {request.user}, "{invitation.moogt}" has started')

            if request.user != inviter:
                notify.send(
                    recipient=inviter,
                    sender=request.user,
                    verb='has started',
                    target=invitation.moogt,
                    type=NOTIFICATION_TYPES.moogt_status,
                    send_email=False,
                    send_telegram=True,
                    data={'moogt': MoogtNotificationSerializer(
                        invitation.moogt).data},
                    push_notification_title='Moogt Started!',
                    push_notification_description=f'Your Moogt with {request.user}, "{invitation.moogt}" has started')

            update_invitation_notification(invitation)

            return Response('Successfully updated invitation')


class ModeratorInvitationActionAPIView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView):
    http_method_names = ['post']
    serializer_class = ModeratorInvitationSerializer

    def post(self, request, *args, **kwargs):
        moderator_invitation_id = kwargs.get('pk', None)
        moderator_invitation = get_object_or_404(
            ModeratorInvitation, pk=moderator_invitation_id)
        try:
            action = request.data.get('action')
            if action == 'accept':
                if not moderator_invitation.get_status() == ModeratorInvititaionStatus.pending():
                    raise ValidationError(
                        'You cannnot accept the request')

                moderator_invitation.invitation.moogt.set_moderator(
                    self.request.user)
                moderator_invitation.set_moderator(self.request.user)
                moderator_invitation.set_status(
                    ModeratorInvititaionStatus.accepted())

                moderator_invitation.invitation.moogt.save()
                moderator_invitation.save()
                moderator_invitation.invitation.save()

                moderator_invitation_message = moderator_invitation.moderator_message
                if moderator_invitation_message:
                    moderator_invitation_message.summaries.create(
                        actor=moderator_invitation.get_moderator(), verb=MessageSummary.VERBS.ACCEPT.value)

                notify.send(
                    recipient=moderator_invitation.invitation.get_inviter(),
                    sender=request.user,
                    verb='has accepted',
                    target=moderator_invitation,
                    action_object=moderator_invitation.moderator_message.conversation,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.accept_moderator_invitation,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    data={
                        'moderator_invitation': ModeratorInvitationNotificationSerializer(moderator_invitation).data,
                        'invitation': InvitationNotificationSerializer(moderator_invitation.invitation).data
                    },
                    push_notification_title=f'{request.user} Accepted Invite to Moderate!',
                    push_notification_description=f'{request.user} accepted the invite to Moderate the Moogt, "{moderator_invitation.invitation.moogt}"'
                )

                notify.send(
                    recipient=moderator_invitation.invitation.get_invitee(),
                    sender=request.user,
                    verb='has accepted',
                    target=moderator_invitation,
                    action_object=moderator_invitation.moderator_message.conversation,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.accept_moderator_invitation,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    data={
                        'moderator_invitation': ModeratorInvitationNotificationSerializer(moderator_invitation).data,
                        'invitation': InvitationNotificationSerializer(moderator_invitation.invitation).data
                    },
                    push_notification_title=f'{request.user} Accepted Invite to Moderate!',
                    push_notification_description=f'{request.user} accepted the invite to Moderate the Moogt, "{moderator_invitation.invitation.moogt}"'
                )

                update_moderator_invitation_notification(moderator_invitation)
                return Response(self.get_serializer(moderator_invitation).data, status=status.HTTP_200_OK)

            if action == 'decline':
                if not moderator_invitation.get_status() == ModeratorInvititaionStatus.pending():
                    raise ValidationError(
                        'You cannnot decline the request')
                moderator_invitation.set_status(
                    ModeratorInvititaionStatus.declined())

                moderator_invitation.save()
                moderator_invitation.invitation.save()

                moderator_invitation_message = moderator_invitation.moderator_message
                if moderator_invitation_message:
                    moderator_invitation_message.summaries.create(
                        actor=moderator_invitation.get_moderator(), verb=MessageSummary.VERBS.DECLINE.value)

                notify.send(
                    recipient=moderator_invitation.invitation.get_inviter(),
                    sender=request.user,
                    verb='has declined',
                    target=moderator_invitation,
                    action_object=moderator_invitation.moderator_message.conversation,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.decline_moderator_invitation,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    data={
                        'moderator_invitation': ModeratorInvitationNotificationSerializer(moderator_invitation).data,
                        'invitation': InvitationNotificationSerializer(moderator_invitation.invitation).data
                    },
                    push_notification_title=f'{request.user} Declined Invite to Moderate!',
                    push_notification_description=f'{request.user} declined the invite to Moderate the Moogt. "{moderator_invitation.invitation.moogt}"'
                )

                notify.send(
                    recipient=moderator_invitation.invitation.get_invitee(),
                    sender=request.user,
                    verb='declined',
                    target=moderator_invitation,
                    action_object=moderator_invitation.moderator_message.conversation,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.decline_moderator_invitation,
                    category=Notification.NOTIFICATION_CATEGORY.normal,
                    data={
                        'moderator_invitation': ModeratorInvitationNotificationSerializer(moderator_invitation).data,
                        'invitation': InvitationNotificationSerializer(moderator_invitation.invitation).data
                    }
                )
                update_moderator_invitation_notification(
                    moderator_invitation)

                return Response(self.get_serializer(moderator_invitation).data, status=status.HTTP_200_OK)

            if action == 'cancel':
                if not moderator_invitation.get_status() == ModeratorInvititaionStatus.pending():
                    raise ValidationError(
                        'You cannnot cancel the request')
                moderator_invitation.set_status(
                    ModeratorInvititaionStatus.cancelled())

                moderator_invitation.save()
                moderator_invitation.invitation.save()

                moderator_invitation_message = moderator_invitation.moderator_message
                if moderator_invitation_message:
                    moderator_invitation_message.summaries.create(
                        actor=moderator_invitation.invitation.get_inviter(), verb=MessageSummary.VERBS.CANCEL.value)

                return Response(self.get_serializer(moderator_invitation).data, status=status.HTTP_200_OK)

            raise rest_framework.exceptions.ValidationError(
                'Invalid attempt to accept moderator invitation.')
        except django.core.exceptions.ValidationError as err:
            raise rest_framework.exceptions.ValidationError(err)
