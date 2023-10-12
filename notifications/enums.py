from model_utils import Choices

# The type of this notification object
NOTIFICATION_TYPES = Choices(  # moogt
    'moogt_status',
    'moogt_request',
    'moogt_request_resolved',
    'moogt_card',
    'moogt_follow',
    'moogt_premiere',
    'moogt_conclude',

    'mini_suggestion_new',
    'mini_suggestion_action',

    'invitation_sent',
    'invitation_start_anytime',
    'invitation_accept_invitee',
    'invitation_accept_inviter',

    'view_applaud',
    'view_comment',
    'view_agree',
    'view_disagree',

    'argument_applaud',
    'argument_comment',
    'argument_agree',
    'argument_disagree',
    'argument_request',
    'argument_request_resolved',

    'poll_vote',
    'poll_comment',
    'poll_closed',

    'comment_applaud',
    'comment_reply',

    'user_follow',

    'regular_message',

    'moderator_request',
    'accept_moderator_invitation',
    'decline_moderator_invitation',
    
    'user_warned',
)
