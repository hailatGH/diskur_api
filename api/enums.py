from enum import Enum


class Visibility(Enum):
    PUBLIC = 'To the public'
    FOLLOWERS_ONLY = 'To my subscribers only'

    @classmethod
    def all(cls):
        return [{'name': status.name, 'value': status.value} for status in cls]


class ViewType(Enum):
    VIEW = 'View'
    VIEW_REACTION = 'View reaction view'
    ARGUMENT_REACTION = 'Argument reaction view'


class ReactionType(Enum):
    ENDORSE = "Endorse"
    DISAGREE = "Disagree"
    APPLAUD = "Applaud"


class InvitationType(Enum):
    SENT = "Sent Invitations"
    RECEIVED = "Received Invitations"


class ShareProvider(Enum):
    FACEBOOK = 'facebook'