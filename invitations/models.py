from django.core.exceptions import ValidationError
from django.db import models

from django.shortcuts import get_object_or_404
from django.utils import timezone

from meda.enums import InvitationStatus
from meda.enums import ModeratorInvititaionStatus
from invitations.managers import InvitationManager, ModeratorInvitationManager
from moogts.models import Moogt
from users.models import MoogtMedaUser
from meda.behaviors import Timestampable


class Invitation(models.Model):
    """Represents invitation to a Moogt. """

    # The moogt associated with this invitation.
    moogt = models.ForeignKey(Moogt,
                              related_name='invitations',
                              on_delete=models.CASCADE)

    # Person sending invitation. If the user is deleted, this invitation
    # will also be deleted.
    inviter = models.ForeignKey(MoogtMedaUser,
                                related_name='sent_invitations',
                                null=True,
                                on_delete=models.CASCADE)

    # Person to whom this invitation is sent. If this user is deleted, this invitation
    # will also be deleted.
    invitee = models.ForeignKey(MoogtMedaUser,
                                related_name='received_invitations',
                                null=True,
                                on_delete=models.CASCADE)

    # The status of this invitation. Will be set to PENDING by default.
    status = models.CharField(
        default=InvitationStatus.pending(),
        null=True,
        max_length=50,
        choices=[(status.name, status.value) for status in InvitationStatus])

    # The date/time when this invitation was created.
    created_at = models.DateTimeField(default=timezone.now)

    # The last update time for this invitation.
    updated_at = models.DateTimeField(auto_now=True)

    # The parent of this invitation if this invitation was created after editing another invitation.
    parent_invitation = models.OneToOneField('self',
                                             related_name='child_invitation',
                                             on_delete=models.SET_NULL,
                                             null=True)

    objects = InvitationManager()

    @staticmethod
    def validate_invitation(moogt, inviter, invitee):
        # Don't invite your self!
        if inviter == invitee:
            raise ValidationError("Invitation sent to sender.")

        # Don't invite someone to someone else's moogt.
        if inviter != moogt.get_proposition():
            raise ValidationError("Inviter should be Moogt creator.")

        # Don't invite someone to a moogt thas already has an invitation.
        for invitation in moogt.invitations.all():
            if (invitation.status == InvitationStatus.pending() or
                    invitation.status == InvitationStatus.accepted()):
                raise ValidationError(
                    "Moogt has pending or accepted invitation")

        # Don't invite someone to a moogt that already has opposition
        if moogt.get_opposition() is not None:
            raise ValidationError("Moogt already has opposition")

    @staticmethod
    def create(moogt, invitee_id, inviter):
        invitee = get_object_or_404(MoogtMedaUser, pk=invitee_id)
        invitation = Invitation(moogt=moogt, inviter=inviter, invitee=invitee)

        Invitation.validate_invitation(moogt, inviter, invitee)

        invitation.save()

        return invitation

    def __str__(self):
        return "Moogt: %s, Inviter: %s, Invitee: %s" % (self.moogt.get_resolution()[:50],
                                                        self.inviter,
                                                        self.invitee)

    def get_moogt(self):
        return self.moogt

    def set_moogt(self, value):
        self.moogt = value

    def get_inviter(self):
        return self.inviter

    def set_inviter(self, value):
        self.inviter = value

    def get_invitee(self):
        return self.invitee

    def set_invitee(self, value):
        self.invitee = value

    def get_status(self):
        return self.status

    def set_status(self, value):
        self.status = value

    def get_created_at(self):
        return self.created_at

    def set_created_at(self, value):
        self.created_at = value

    def get_updated_at(self):
        return self.updated_at

    def set_updated_at(self, value):
        self.updated_at = value

    @staticmethod
    def create(inviter, invitee, moogt, commit=True):
        invitation = Invitation(invitee=invitee, inviter=inviter, moogt=moogt)

        if commit:
            invitation.save()

        return invitation

    def validate(self):
        if self.get_inviter() is None or self.get_invitee() is None:
            raise ValidationError('Invitee/Inviter has not been set.')

        # Don't invite your self!
        if self.get_inviter() == self.get_invitee():
            raise ValidationError('Invitation sent to sender.')

        if self.get_moogt() is None:
            raise ValidationError('Moogt has not been set.')

        # Don't invite someone to someone else's moogt.
        # if self.get_inviter() != self.moogt.get_proposition():
        #     raise ValidationError('Inviter should be Moogt creator.')

        # Don't invite someone to a moogt that already has opposition
        # if self.get_moogt().get_opposition() is not None:
        #     raise ValidationError('Moogt already has opposition')

        # Don't invite someone to a moogt that already has an invitation.
        # for invitation in self.moogt.invitations.all():
        #     if invitation.get_status() == InvitationStatus.pending() or \
        #             invitation.get_status() == InvitationStatus.accepted():
        #         raise ValidationError(
        #             'Moogt has pending or accepted invitation.')

    def validate_invitation_open(self):
        if self.status != InvitationStatus.pending():
            raise ValidationError("Can only update pending invitation.")

    def validate_updater_is_invitee(self, updater):
        if self.invitee != updater:
            raise ValidationError('User not authorized to update invitation.')

    def validate_updater_is_inviter(self, updater):
        if self.inviter != updater:
            raise ValidationError('User not authorized to update invitation.')


class ModeratorInvitation(Timestampable):
    # The user suggested to be the moderator. If accepted this will be the moderator for the moogt.
    moderator = models.ForeignKey(
        MoogtMedaUser, related_name='+', on_delete=models.CASCADE)

    # The status of this moderator suggestion. It will be pending by default.
    status = models.CharField(default=ModeratorInvititaionStatus.pending(),
                              max_length=50,
                              choices=[(status.name, status.value) for status in ModeratorInvititaionStatus])

    invitation = models.OneToOneField(
        Invitation, related_name='moderator_invitation', on_delete=models.CASCADE, null=False)

    objects = ModeratorInvitationManager()

    def validate(self, invitee, inviter):
        if self.moderator == invitee or self.moderator == inviter:
            raise ValidationError('Moderator can never be inviter or invitee')

    def get_moderator(self):
        return self.moderator

    def set_moderator(self, moderator):
        self.moderator = moderator

    def set_status(self, status):
        self.status = status

    def get_status(self):
        return self.status
