from enum import Enum


class ArgumentActivityType(Enum):
    EDIT = "Edit"
    DELETE = "Delete"


class ArgumentReactionType(Enum):
    ENDORSEMENT = "Endorsement"
    DISAGREEMENT = "Disagreement"
