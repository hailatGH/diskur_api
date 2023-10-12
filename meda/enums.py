from enum import Enum


class MoogtEndStatus(Enum):
    """Represents the end status of a Moogt."""
    # A user wishes to concede the debate.
    CNCD = "Concede"
    # A user wishes to 'agree-to-disagree'. In this case the other moogter
    # gets the last word.
    DSGR = "Disagree"

    def concede():
        return __class__.CNCD.name

    def disagree():
        return __class__.DSGR.name


class InvitationStatus(Enum):
    """Represents the status of an Invitation."""
    # Invitation sent but not yet accepted or declined.
    PENDING = "Pending"
    # Invitation accepted by invitee.
    ACCEPTED = "Accepted"
    # Invitation declined by invitee.
    DECLINED = "Declined"
    # Invitation cancelled by inviter.
    CANCELLED = "Cancelled"
    # Invitation edited by invitee.
    EDITED = "EDITED"
    # Invitation is revised.
    REVISED = 'REVISED'
    # A started invitation.
    STARTED = "STARTED"

    # Invitation accepted by one of the invitees, waiting for the other one.
    ACCEPTED_BY_ONE_INVITEE = "ACCEPTED_BY_ONE_INVITEE"

    def pending():
        return __class__.PENDING.name

    def accepted():
        return __class__.ACCEPTED.name

    def accepted_by_one_invitee():
        return __class__.ACCEPTED_BY_ONE_INVITEE.name

    def declined():
        return __class__.DECLINED.name

    def cancelled():
        return __class__.CANCELLED.name

    def edited():
        return __class__.EDITED.name

    def revised():
        return __class__.REVISED.name

    def started():
        return __class__.STARTED.name


class ModeratorInvititaionStatus(Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"

    def pending():
        return __class__.PENDING.name

    def accepted():
        return __class__.ACCEPTED.name

    def declined():
        return __class__.DECLINED.name

    def cancelled():
        return __class__.CANCELLED.name


class MoogtType(Enum):
    DUO = "Duo Moogt"
    GROUP = "Group Moogt"


class ArgumentType(Enum):
    # An argument of this type is created whenever two people are debating.
    NORMAL = "Normal Argument"

    # AN argument of moderator type
    MODERATOR_ARGUMENT = "Moderator Argument"

    # An argument of this type is created to indicate the argument is the final conclusion statement.
    CONCLUDING = "Concluding Argument"

    # An argument of this type is created when an argument is deleted
    DELETED = "Deleted Argument"

    # An argument that is created when you waive your turn.
    WAIVED = 'Waived Argument'

    # A reaction argument
    REACTION = 'Reaction Argument'

    # A card created when you miss your turn.
    MISSED_TURN = 'Missed Turn'

    # A card created when a moogt starts
    MOOGT_STARTED = 'Moogt Started'

    # A card created when a moogt is paused
    MOOGT_PAUSED = 'Moogt Paused'

    # When a moogt is auto paused.
    AUTO_PAUSED = 'Moogt automatically paused.'

    # A card created when a paused moogt is resumed
    MOOGT_RESUMED = 'Moogt Resumed'

    # A card created when a moogt is broke off
    MOOGT_BROKE_OFF = 'Moogt Broke Off'

    # A card created when a moogt is ended
    MOOGT_ENDED = 'Moogt Ended'

    # A card created when a moogt is over
    MOOGT_OVER = 'Moogt Over'

    # A card created when a moogter is reacting on card without statement
    REACTION_WITHOUT_STATEMENT = 'Argument Reacted Without Statement'


class ActivityStatus(Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"
    WAITING = "Waiting"
