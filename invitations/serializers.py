from rest_framework import serializers
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin

from invitations.models import Invitation, ModeratorInvitation
from users.serializers import MoogtMedaUserSerializer


class InvitationNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    banner = serializers.SerializerMethodField()
    moogt = serializers.StringRelatedField()
    inviter = MoogtMedaUserSerializer()
    invitee = MoogtMedaUserSerializer()

    class Meta:
        model = Invitation
        fields = ['id', 'inviter', 'invitee', 'banner', 'moogt', 'status']

    def get_banner(self, invitation):
        from moogts.serializers import MoogtBannerSerializer
        return MoogtBannerSerializer(invitation.moogt.banner).data


class ModeratorInvitationNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    moderator = MoogtMedaUserSerializer()

    class Meta:
        model = ModeratorInvitation
        fields = ['id', 'moderator', 'status', 'created_at',
                  'updated_at']


class InvitationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):

    inviter = MoogtMedaUserSerializer(read_only=True)
    invitee = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = Invitation
        fields = ['id', 'moogt', 'inviter', 'invitee', 'inviter_id', 'invitee_id',
                  'status', 'created_at', 'updated_at']
        expandable_fields = dict(
            moogt=dict(
                serializer='moogts.serializers.MoogtSerializer', read_only=True),
            moderator_invitation=dict(
                serializer='invitations.serializers.ModeratorInvitationSerializer', read_only=True)

        )


class ModeratorInvitationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    moderator = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = ModeratorInvitation
        fields = ['id', 'moderator', 'moderator_id', 'status', 'created_at',
                  'updated_at', ]

        expandable_fields = dict(
            invitation=dict(
                serializer=InvitationSerializer, read_only=True),
        )
