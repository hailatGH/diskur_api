class BasicInvitationExtensions:
    extensions_expand = {'inviter', 'inviter__profile',
                         'invitee', 'invitee__profile'}


class BasicModeratorInvitationExtensions:
    extensions_expand = {'moderator', 'moderator__profile'}
