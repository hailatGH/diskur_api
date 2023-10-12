from django.db.models import Manager


class InvitationManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'inviter',
            'inviter__profile',
            'invitee',
            'invitee__profile',
        )


class ModeratorInvitationManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'moderator',
            'moderator__profile',
        )
