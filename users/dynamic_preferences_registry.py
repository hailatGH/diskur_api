from dynamic_preferences.types import BooleanPreference, StringPreference
from dynamic_preferences.preferences import Section
from dynamic_preferences.registries import global_preferences_registry
from dynamic_preferences.users.registries import user_preferences_registry

# Sections to group related preferences together
email = Section('email')

# Per-user preference
@user_preferences_registry.register
class EmailNotificationForInvitationEnabled(BooleanPreference):
    """Receive email notifications for Moogt invitations?"""
    section = email
    name = 'email_when_invited_enabled'
    verbose_name = 'Receive email notifications for Moogt invitations?'
    default = True


@user_preferences_registry.register
class EmailNotificationWhenNewArgumentAddedEnabled(BooleanPreference):
    """Receive email notifications when a new Argument is added to a Moogt in which
     the user is participating (i.e. user is proposition or opposition)."""
    section = email
    name = 'email_when_argument_added_enabled'
    verbose_name = 'Receive email notifications when a new Argument is added?'
    default = True
