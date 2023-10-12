import datetime
import uuid

from django.utils import timezone
from users.models import MoogtMedaUser, Profile

from moogts.models import Moogt
from arguments.models import Argument, ArgumentStats


# Create your tests here.
def create_moogt(resolution=None, started_at_days_ago=None,
                 opposition=False,
                 latest_argument_added_at_hours_ago=None,
                 has_ended=False,
                 has_opening_argument=False,
                 reply_time=timezone.timedelta(hours=3),
                 moogt_duration=timezone.timedelta(days=2),
                 is_paused=False):
    moogt = Moogt()
    proposition_user = MoogtMedaUser(username=uuid.uuid4().hex[:6].lower())
    proposition_user.save()
    profile = Profile()
    profile.user = proposition_user
    profile.save()

    moogt.set_proposition(proposition_user)

    # This is in case the default values are changed in the future
    moogt.set_max_duration(moogt_duration)
    moogt.set_idle_timeout_duration(reply_time)

    if started_at_days_ago is not None:
        started_at_time = timezone.now() - datetime.timedelta(days=started_at_days_ago)
        moogt.set_started_at(started_at_time)

    if opposition:
        opposition_user = MoogtMedaUser(username=uuid.uuid4().hex[:6].lower())
        opposition_user.save()

        profile = Profile()
        profile.user = opposition_user
        profile.save()

        moogt.set_opposition(opposition_user)

    if latest_argument_added_at_hours_ago is not None:
        latest_argument_added_at_time = timezone.now().replace(second=0, microsecond=0) - \
            timezone.timedelta(hours=latest_argument_added_at_hours_ago)
        moogt.set_latest_argument_added_at(latest_argument_added_at_time)

    if has_ended:
        moogt.set_has_ended(True)

    if resolution is not None:
        moogt.set_resolution(resolution)
    
    moogt.is_paused = is_paused

    moogt.save()

    if has_opening_argument:
        argument = Argument(moogt=moogt, user=proposition_user, argument='argument')
        argument.save()

        stats = ArgumentStats()
        stats.argument = argument
        stats.save()

    return moogt
