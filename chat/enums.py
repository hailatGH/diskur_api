from enum import Enum


class WebSocketMessageType(Enum):
    CONVERSATION_CREATED = 'conversation_created'
    CONVERSATION_UPDATED = 'conversation_updated'
    MESSAGE = 'message'
    SUMMARY_CREATED = 'summary_created'
    MESSAGE_READ = 'message_read'
    ARGUMENT = 'argument'


class MessageType(Enum):
    REGULAR_MESSAGE = 'regular_message'
    MINI_SUGGESTION_MESSAGE = 'mini_suggestion_message'
    INVITATION_MESSAGE = 'invitation_message'
    MODERATOR_INVITATION_MESSAGE = 'moderator_invitation_message'


class ConversationType(Enum):
    PRIORITY = 'priority'
    GENERAL = 'general'
