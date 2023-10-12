import datetime
import io
import uuid
from contextlib import contextmanager
from unittest import mock

from PIL import Image
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django_comments_xtd.conf import settings
from django_comments_xtd.models import XtdComment

from api.enums import Visibility, ReactionType, ViewType
from api.mixins import ViewArgumentReactionMixin
from arguments.models import Argument, ArgumentStats, ArgumentActivity, ArgumentType
from chat.models import Conversation, Participant, RegularMessage
from invitations.models import Invitation
from meda.enums import InvitationStatus
from invitations.models import ModeratorInvitation
from meda.enums import ModeratorInvititaionStatus
from moogts.models import Moogt, MoogtMiniSuggestion, MoogtStats
from polls.models import Poll, PollOption, PollScore
from users.models import MoogtMedaUser, Profile, Activity
from views.models import View, ViewScore, ViewStats


def create_user(username, password):
    user = MoogtMedaUser(username=username)
    user.set_password(password)
    user.first_name = 'test_first_name'
    user.email = 'test@email.com'
    user.save()

    profile = Profile()
    profile.user = user
    profile.save()

    return user


def create_user_and_login(obj, username='testuser', password='testpassword'):
    user = create_user(username, password)
    # This will bypass authentication and force the request to be treated as authenticated
    obj.client.force_login(user)
    return user


def create_invitation(moogt, invitation_status=InvitationStatus.pending(), invitee=None, inviter=None):
    invitation = Invitation(
        moogt=moogt, status=invitation_status, invitee=invitee, inviter=inviter)
    invitation.save()

    return invitation


def create_moderator_invitation(invitation_status=ModeratorInvititaionStatus.pending(), moderator=None, invitation=None):
    moderator_invitation = ModeratorInvitation(
        status=invitation_status, moderator=moderator, invitation=invitation)

    moderator_invitation.save()

    return moderator_invitation


def create_moogt_with_user(proposition_user, resolution=None, started_at_days_ago=None,
                           opposition=None, latest_argument_added_at_hours_ago=None,
                           has_ended=False, create_invitation=True, visibility=Visibility.PUBLIC.name,
                           has_opening_argument=False, ):
    moogt = Moogt()
    profile = Profile()
    profile.user = proposition_user
    profile.save()

    moogt.set_proposition(proposition_user)

    # This is in case the default values are changed in the future
    moogt.set_max_duration(timezone.timedelta(days=2))
    moogt.set_idle_timeout_duration(timezone.timedelta(hours=3))

    if started_at_days_ago is not None:
        started_at_time = timezone.now() - datetime.timedelta(days=started_at_days_ago)
        moogt.set_started_at(started_at_time)

    if opposition == True:
        opposition = MoogtMedaUser(username=uuid.uuid4().hex[:6].lower())
        opposition.save()

        profile = Profile()
        profile.user = opposition
        profile.save()

        moogt.set_opposition(opposition)
    elif opposition != None:
        profile = Profile()
        profile.user = opposition
        profile.save()

        moogt.set_opposition(opposition)

    if latest_argument_added_at_hours_ago is not None:
        latest_argument_added_at_time = timezone.now().replace(second=0, microsecond=0) - \
            timezone.timedelta(hours=latest_argument_added_at_hours_ago)
        moogt.set_latest_argument_added_at(latest_argument_added_at_time)

    if has_ended:
        moogt.set_has_ended(True)

    if resolution is not None:
        moogt.set_resolution(resolution)

    moogt.visibility = visibility
    moogt.save()

    if create_invitation:
        invitation = Invitation(
            moogt=moogt, invitee=proposition_user, inviter=opposition)
        invitation.save()

    if has_opening_argument:
        argument = Argument(
            moogt=moogt, user=proposition_user, argument='argument')
        argument.save()

        moogt.next_turn_proposition = False
        moogt.save()

        stats = ArgumentStats()
        stats.argument = argument
        stats.save()

    return moogt


def create_argument(user, argument, moogt=None, moogt_has_ended=False, reply_to=None, modified_child_argument=None,
                    type=ArgumentType.NORMAL.name):
    if not moogt:
        moogt = create_moogt_with_user(
            user, resolution="test moogt resolution")
    argument = Argument(moogt=moogt, user=user, argument=argument)
    if reply_to:
        argument.reply_to = reply_to

    if modified_child_argument:
        child_argument = Argument(
            moogt=moogt, user=user, argument=modified_child_argument)
        child_argument.save()
        argument.modified_child = child_argument

    moogt: Moogt = argument.moogt
    moogt.has_ended = moogt_has_ended

    if argument.moogt.opposition == user:
        moogt.next_turn_proposition = True
    elif argument.moogt.proposition == user:
        moogt.next_turn_proposition = False
    moogt.save()

    argument.type = type

    argument.save()

    moogt.latest_argument_added_at = argument.created_at
    moogt.save()

    stats = ArgumentStats()
    stats.argument = argument
    stats.save()

    return argument


def create_argument_activity(user, type, status, argument=None):
    if not argument:
        argument = create_argument(user, "argument")
    activity = ArgumentActivity(
        argument=argument, type=type, status=status, user=user)
    activity.save()
    return activity


def create_view(user, content=None, visibility=Visibility.PUBLIC.name, comment_disabled=False, hidden=False):
    view = View()
    view.user = user
    view.content = content
    view.visibility = visibility
    view.user = user
    view.is_hidden = hidden
    view.is_comment_disabled = comment_disabled
    view.save()

    view_stats = ViewStats()
    view_stats.set_view(view)
    view_stats.save()

    view_score = ViewScore(view=view)
    view_score.save()

    return view


def create_reaction_view(user,
                         parent,
                         content=None,
                         reaction_type=ReactionType.ENDORSE.name,
                         type=ViewType.VIEW_REACTION.name,
                         visibility=Visibility.PUBLIC.name,
                         hidden=False):
    reaction_view = create_view(user, content=content, visibility=visibility)
    if isinstance(parent, View):
        reaction_view.parent_view = parent
    elif isinstance(parent, Argument):
        reaction_view.parent_argument = parent
    reaction_view.type = type
    reaction_view.reaction_type = reaction_type
    reaction_view.is_hidden = hidden
    reaction_view.save()

    if isinstance(parent, Argument):
        ViewArgumentReactionMixin.update_argument(parent)

    return reaction_view


def create_poll(user,
                title,
                option_array=[{"content": "option 1"},
                              {"content": "option 2"},
                              {"content": "option 3"},
                              {"content": "option 4"}],
                start_date=timezone.now(),
                end_date=timezone.now() + timezone.timedelta(days=2),
                visibility=Visibility.PUBLIC):
    poll = Poll()
    poll.user = user
    poll.title = title
    poll.start_date = start_date
    poll.end_date = end_date
    poll.visibility = visibility
    poll.save()

    poll_score = PollScore(poll=poll)
    poll_score.save()

    # create options
    options = []
    if len(option_array) > 4 or len(option_array) < 2:
        raise ValueError("Options can not be less than 2 or greater than 4.")
    for i in option_array:
        options.append(PollOption(poll=poll, content=i.get('content')))

    PollOption.objects.bulk_create(options)

    return Poll.objects.get(pk=poll.id)


def create_activity(profile, activity_type, object_id):
    activity = Activity()
    activity.profile = profile
    activity.type = activity_type
    activity.object_id = object_id
    activity.save()
    return activity


def create_comment(obj, user, comment):
    ctype = ContentType.objects.get_for_model(obj)
    comment = XtdComment(content_type=ctype,
                         user=user,
                         object_pk=obj.pk,
                         thread_id=obj.pk,
                         comment=comment,
                         site_id=settings.SITE_ID)
    comment.save()
    if isinstance(obj, View) or isinstance(obj, Argument) or isinstance(obj, Poll):
        obj.comment_count = obj.comment_count + 1
        obj.save()
    return comment


def create_conversation(participants):
    conversation = Conversation.objects.create()

    for user in participants:
        conversation.add_participant(
            user=user, role=Participant.ROLES.MODERATOR.value)

    return conversation


def create_regular_message(user, content, conversation: Conversation):
    message = RegularMessage(content=content, user=user,
                             conversation=conversation)
    message.save()
    conversation.last_message = message.content
    conversation.save()
    return message


def create_mini_suggestion(moogt, suggester, resolution=None,
                           moderator=None, max_duration=None,
                           visiblity=None, description=None,
                           idle_timeout_duration=None):
    suggestion = MoogtMiniSuggestion(moogt=moogt,
                                     user=suggester,
                                     resolution=resolution,
                                     moderator=moderator,
                                     description=description,
                                     max_duration=max_duration,
                                     visibility=visiblity,
                                     idle_timeout_duration=idle_timeout_duration)

    suggestion.save()
    return suggestion


def create_moogt_stats(moogt):
    stats = MoogtStats()
    stats.set_moogt(moogt)
    stats.set_view_count(0)
    stats.save()
    return stats


def generate_photo_file(width=630, height=210):
    # https://gist.github.com/guillaumepiot/817a70706587da3bd862835c59ef584e
    file = io.BytesIO()
    image = Image.new('RGBA', size=(width, height), color=(255, 255, 255))

    image.save(file, 'png')
    file.name = 'test.png'
    file.seek(0)
    return file


@contextmanager
def catch_signal(signal):
    """Catch django signal and return the mocked call."""
    handler = mock.Mock()
    signal.connect(handler)
    try:
        yield handler
    finally:
        signal.disconnect()
