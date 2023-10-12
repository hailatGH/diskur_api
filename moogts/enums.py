from enum import Enum

from model_utils import Choices

MOOGT_WEBSOCKET_EVENT = Choices('start_is_typing', 'user_is_typing')


class MiniSuggestionState(Enum):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    DISAPPROVED = 'Disapproved'
    CANCEL = 'cancel'
    EDITED = 'edited'

    @classmethod
    def all(cls):
        return [{'name': status.name, 'value': status.value} for status in cls]


class MoogtActivityType(Enum):
    CARD_REQUEST = 'CARD_REQUEST'
    END_REQUEST = 'END_REQUEST'
    PAUSE_REQUEST = 'PAUSE_REQUEST'
    RESUME_REQUEST = 'RESUME_REQUEST'
    DELETE_REQUEST = 'DELETE_REQUEST'
    ENDORSEMENT = 'ENDORSEMENT'
    DISAGREEMENT = 'DISAGREEMENT'
    QUIT = 'QUIT'

    @classmethod
    def all(cls):
        return [{'name': status.name, 'value': status.value} for status in cls]


class DonationLevel(Enum):
    """Represents the donation level."""

    LEVEL_1 = 'Level One'
    LEVEL_2 = 'Level Two'
    LEVEL_3 = 'Level Three'
    LEVEL_4 = 'Level Four'
    LEVEL_5 = 'Level Five'

    @classmethod
    def all(cls):
        return [(role.name, role.value) for role in cls]


class MoogtWebsocketMessageType(Enum):
    ARGUMENT_CREATED = "argument_created"
    ARGUMENT_DELETED = "argument_deleted"
    ARGUMENT_UPDATED = "argument_updated"
    ARGUMENT_REACTION = "argument_reaction"
    MOOGT_UPDATED = "moogt_updated"
    DONATION_MADE = 'donation_made'
    ARGUMENT_DELETE_APPROVED = 'argument_delete_approved'
    ARGUMENT_DELETE_CANCELLED = 'argument_delete_cancelled'
    ARGUMENT_EDIT_APPROVED = 'argument_edit_approved'
    ARGUMENT_EDIT_CANCELLED = 'argument_edit_cancelled'