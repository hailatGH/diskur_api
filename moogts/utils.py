from django.db.models import Q
from queryset_sequence import QuerySetSequence

from moogts.enums import MoogtWebsocketMessageType
from meda.utils import group_send
from moogts.models import Moogt, MoogtStatus
from users.models import MoogtMedaUser


async def notify_ws_clients(moogt, message_type=MoogtWebsocketMessageType.MOOGT_UPDATED.value):
    """
    Inform clients there is an update in moogt
    """
    notification = {
        'type': 'receive_group_message',
        'moogt_id': moogt.id,
        'event_type': message_type
    }

    await group_send(moogt, notification)


def _create_moogt_over_status(moogt_ids):
    moogt_statuses = list(map(lambda x: MoogtStatus(
        moogt_id=x, status=MoogtStatus.STATUS.broke_off), moogt_ids))

    MoogtStatus.objects.bulk_create(moogt_statuses)


def find_and_quit_moogts(quitter, opponent_user):
    moogt_queryset = Moogt.objects.get_live_moogts().get_user_moogts(
        quitter).get_user_moogts(opponent_user)

    quit_moogts(moogt_queryset, quitter)


def maybe_unfollow_moogts(follower):
    blocker_query = Q(proposition__blockers__user=follower) & Q(
        opposition__blockers__user=follower)
    blocker_moogts = Moogt.objects.filter(Q(Q(moderator__isnull=True) & blocker_query) | Q(
        Q(moderator__isnull=False) & blocker_query & Q(moderator__blockers__user=follower)))

    blocked_query = Q(proposition__blockings__blocked_user=follower) & Q(
        opposition__blockings__blocked_user=follower)
    blocked_moogts = Moogt.objects.filter(Q(Q(moderator__isnull=True) & blocked_query) | Q(
        Q(moderator__isnull=False) & blocked_query & Q(moderator__blockings__blocked_user=follower)))

    moogt_ids = QuerySetSequence(
        blocker_moogts, blocked_moogts).values_list('id', flat=True)

    ThroughModel = MoogtMedaUser.following_moogts.through
    ThroughModel.objects.filter(
        moogtmedauser_id=follower.id, moogt_id__in=moogt_ids).delete()


def quit_moogts(moogt_queryset, quitter):
    moogt_queryset.update(
        quit_by=quitter, next_turn_proposition=~Q(proposition=quitter))

    moogt_ids = moogt_queryset.values_list('id', flat=True)

    _create_moogt_over_status(moogt_ids=moogt_ids)


def get_awaited_user(requesting_user, acting_user, moogt):
    users = [moogt.get_opposition(), moogt.get_moderator(),
             moogt.get_proposition()]
    filtered_user = filter(lambda user: user !=
                           requesting_user and user != acting_user, users)
    return list(filtered_user)[0]
