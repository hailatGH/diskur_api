import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from api.enums import ShareProvider
from api.models import ShareStats
from api.tests.utility import create_argument, create_user

from meda.enums import MoogtEndStatus
from meda.tests.test_models import create_moogt
from users.models import MoogtMedaUser
from moogts.models import Moogt, MoogtStatus
from arguments.models import Argument, ArgumentType


class MoogtModelTests(TestCase):

    def test_func_has_expired_with_no_opposition(self):
        """
        func_has_expired() return False if moogt has no opposition
        """
        moogt = create_moogt()
        self.assertIs(moogt.func_has_expired(), False)

    def test_func_has_expired_with_a_moogt_that_has_expired(self):
        """
        func_has_expired() returns True if moogt has expired
        """
        moogt = create_moogt(started_at_days_ago=2, opposition=True)
        self.assertIs(moogt.func_has_expired(), True)

    def test_func_has_expired_with_a_moogt_that_has_not_expired(self):
        """
        func_has_expired() returns False if moogt hasn't expired
        """
        moogt = create_moogt(started_at_days_ago=1, opposition=True)
        self.assertIs(moogt.func_has_expired(), False)

    def test_create_moogt_over_status(self):
        """
        func_create_moogt_over_status creates a moogt over status
        if there is no moogt over status or moogt ended status or
        moogt broke off status created previously
        """
        moogt = create_moogt(started_at_days_ago=1, opposition=True)
        moogt.func_create_moogt_over_status()
        self.assertEqual(MoogtStatus.objects.count(), 1)
        self.assertEqual(MoogtStatus.objects.first().status,
                         MoogtStatus.STATUS.duration_over)

    def test_create_moogt_over_status_on_expired_argument_created_moogt(self):
        """
        func_create_moogt_over_status fails to create a moogt over argument
        if there is a moogt over argument created previously
        """
        moogt = create_moogt(started_at_days_ago=1, opposition=True)

        moogt_ended = Argument(moogt=moogt, argument="",
                               type=ArgumentType.MOOGT_OVER.name)
        moogt_ended.save()

        moogt.func_create_moogt_over_status()

        self.assertEqual(Argument.objects.count(), 1)

    def test_create_moogt_over_status_on_ended_argument_created_moogt(self):
        """
        func_create_moogt_over_status fails to create a moogt over argument
        if there is a moogt ended argument created previously
        """
        moogt = create_moogt(started_at_days_ago=1, opposition=True)

        moogt_ended = MoogtStatus(moogt=moogt, status=MoogtStatus.STATUS.ended)
        moogt_ended.save()

        moogt.func_create_moogt_over_status()

        self.assertEqual(MoogtStatus.objects.count(), 1)

    def test_create_moogt_over_status_on_broke_off_argument_created_moogt(self):
        """
        func_create_moogt_over_status fails to create a moogt over argument
        if there is a moogt ended argument created previously
        """
        moogt = create_moogt(started_at_days_ago=1, opposition=True)

        moogt_ended = MoogtStatus(
            moogt=moogt, status=MoogtStatus.STATUS.broke_off)
        moogt_ended.save()

        moogt.func_create_moogt_over_status()

        self.assertEqual(MoogtStatus.objects.count(), 1)

    def test_func_expire_time_with_a_moogt_that_has_not_started(self):
        """
        func_expire_time() raises a ValidationError if moogt hasn't started
        """
        moogt = create_moogt()
        self.assertRaises(ValidationError, moogt.func_expire_time)

    def test_func_expire_time(self):
        """
        func_expire_time() returns the expire time for a moogt that has started
        """
        moogt = create_moogt(started_at_days_ago=0, opposition=True)
        expire_time = timezone.now().replace(second=0, microsecond=0) + \
            datetime.timedelta(days=2)
        self.assertEqual(moogt.func_expire_time().replace(
            second=0, microsecond=0), expire_time)

    def test_func_overall_clock_time_remaining_with_a_moogt_that_has_not_started(self):
        """
        func_overall_clock_time_remaining() raises a ValidationError
        """
        moogt = create_moogt()
        self.assertRaises(
            ValidationError, moogt.func_overall_clock_time_remaining)

    def test_func_overall_clock_time_remaining_with_a_moogt_that_has_ended(self):
        """
        func_overall_clock_time_remaining() returns timezone.timedelta(0)
        """
        moogt = create_moogt(started_at_days_ago=1,
                             opposition=True, has_ended=True)
        self.assertEqual(
            moogt.func_overall_clock_time_remaining(), timezone.timedelta(0))

    def test_func_overall_clock_time_remaining_with_a_moogt_that_has_expired(self):
        """
        func_overall_clock_time_remaining() returns timezone.timedelta(0)
        """
        moogt = create_moogt(started_at_days_ago=2, opposition=True)
        self.assertEqual(
            moogt.func_overall_clock_time_remaining(), timezone.timedelta(0))

    def test_func_overall_clock_time_remaining_with_a_moogt_that_has_not_expired(self):
        """
        func_overall_clock_time_remaining() returns the clock remaining before a moogt expires
        """
        moogt = create_moogt(started_at_days_ago=0, opposition=True)
        time_left = datetime.timedelta(days=2)
        self.assertAlmostEqual(moogt.func_overall_clock_time_remaining().total_seconds(),
                               time_left.total_seconds(), delta=1.01)

    def test_func_idle_timer_expire_time_remaining_with_argument_that_has_expired(self):
        """
        func_idle_timer_expire_time_remaining() returns timezone.timedelta(0)
        """
        moogt = create_moogt(started_at_days_ago=1,
                             latest_argument_added_at_hours_ago=3)
        self.assertEqual(moogt.func_idle_timer_expire_time_remaining().total_seconds(),
                         timezone.timedelta(0).total_seconds())

    def test_func_idle_timer_expire_time_remaining_with_argument_that_has_not_expired(self):
        """
        func_idle_timer_expire_time_remaining() returns the remaining time
        """
        moogt = create_moogt(started_at_days_ago=1)
        expire_time = timezone.timedelta(hours=3).total_seconds()
        self.assertAlmostEqual(moogt.func_idle_timer_expire_time_remaining().total_seconds(),
                               expire_time, delta=1.01)

    def test_func_idle_timer_expire_time_remaining_with_paused_moogt(self):
        """
        If the moogt is paused the timer shouldn't countdown.
        """
        moogt = create_moogt(started_at_days_ago=1,
                             latest_argument_added_at_hours_ago=2)
        # Pause the moogt
        paused_at = timezone.now()
        moogt.set_is_paused(True)
        moogt.set_paused_at(paused_at)
        moogt.save()

        remaining_time = moogt.func_idle_timer_expire_time_remaining()
        expected_remaining_time = moogt.get_latest_argument_added_at(
        ) + moogt.get_idle_timeout_duration() - paused_at
        self.assertEqual(remaining_time.total_seconds(),
                         expected_remaining_time.total_seconds())

    def test_func_skip_expired_turns_with_a_moogt_that_has_not_started(self):
        """
        func_skip_expired_turns() doesn't change moogt fields.
        """
        moogt = create_moogt(latest_argument_added_at_hours_ago=3)
        added_at_time = timezone.now().replace(second=0, microsecond=0) + \
            datetime.timedelta(hours=-3)
        next_turn_proposition = moogt.get_next_turn_proposition()
        moogt.func_skip_expired_turns()
        self.assertEqual(moogt.get_latest_argument_added_at(), added_at_time)
        self.assertEqual(moogt.get_next_turn_proposition(),
                         next_turn_proposition)

    def test_func_skip_expired_turns_with_a_moogt_that_has_expired(self):
        """
        func_skip_expired_turns() creates expired turns for an expired moogt.
        """
        moogt = create_moogt(
            started_at_days_ago=2, latest_argument_added_at_hours_ago=6, opposition=True)
        moogt.func_skip_expired_turns()
        missed_turn: Argument = moogt.arguments.filter(
            type=ArgumentType.MISSED_TURN.name).first()
        self.assertIsNotNone(missed_turn)
        self.assertEqual(missed_turn.consecutive_expired_turns_count, 2)
        # added_at_time = timezone.now().replace(second=0, microsecond=0) + datetime.timedelta(hours=-3)
        # next_turn_proposition = moogt.get_next_turn_proposition()
        # self.assertEqual(moogt.get_latest_argument_added_at(), added_at_time)
        # self.assertEqual(moogt.get_next_turn_proposition(), next_turn_proposition)

    def test_func_skip_expired_turns_with_a_moogt_that_has_ended(self):
        """
        func_skip_expired_turns() doesn't change moogt fields
        """
        moogt = create_moogt(
            has_ended=True, latest_argument_added_at_hours_ago=3)
        added_at_time = timezone.now().replace(second=0, microsecond=0) + \
            datetime.timedelta(hours=-3)
        next_turn_proposition = moogt.get_next_turn_proposition()
        moogt.func_skip_expired_turns()
        self.assertEqual(moogt.get_latest_argument_added_at(), added_at_time)
        self.assertEqual(moogt.get_next_turn_proposition(),
                         next_turn_proposition)

    def test_func_skip_expired_turns_with_a_moogt_that_has_paused(self):
        """
        func_skip_expired_turns() doesn't create expired turns if the moogt is paused
        """
        moogt = create_moogt(started_at_days_ago=2, opposition=True,
                             is_paused=True, latest_argument_added_at_hours_ago=5)
        moogt.func_skip_expired_turns()
        self.assertEqual(moogt.arguments.count(), 0)

    def test_func_skip_expired_turns_with_a_moogt_that_has_ended(self):
        """
        func_skip_expired_turns() doesn't create expired turns if the moogt has ended.
        """
        moogt = create_moogt(started_at_days_ago=2, opposition=True,
                             has_ended=True, latest_argument_added_at_hours_ago=5)
        moogt.func_skip_expired_turns()
        self.assertEqual(moogt.arguments.count(), 0)

    def test_func_skip_expired_turns_with_an_argument_that_has_expired(self):
        """
        func_skip_expired_turns() should create an empty argument for opposition
        """
        moogt = create_moogt(has_ended=False,
                             latest_argument_added_at_hours_ago=3,
                             opposition=True,
                             started_at_days_ago=1,
                             has_opening_argument=True)
        moogt.func_skip_expired_turns()
        self.assertEqual(moogt.arguments.count(), 2)

    def test_func_skip_expired_turns_with_an_argument_that_has_expired_three_hours_ago(self):
        """
        func_skip_expired_turns() should set next_turn_proposition to False
        """
        moogt = create_moogt(has_ended=False, latest_argument_added_at_hours_ago=3, opposition=True,
                             started_at_days_ago=1)
        moogt.func_skip_expired_turns()
        self.assertFalse(moogt.get_next_turn_proposition())

    def test_func_skip_expired_turns_for_inactive_moogt(self):
        """It pauses the moogt if there is too many missed turns"""
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=3,
                             reply_time=timezone.timedelta(minutes=3),
                             moogt_duration=None)
        latest_argument_added_at = moogt.get_latest_argument_added_at()

        moogt.func_skip_expired_turns()
        missed_turn: Argument = moogt.arguments.filter(
            type=ArgumentType.MISSED_TURN.name).first()

        moogt.refresh_from_db()

        self.assertTrue(moogt.get_is_paused())
        self.assertEqual(missed_turn.consecutive_expired_turns_count, 60)
        self.assertEqual(moogt.get_paused_at(),
                         latest_argument_added_at +
                         missed_turn.consecutive_expired_turns_count * moogt.get_idle_timeout_duration())

    def test_func_skip_expired_turns_should_not_pause_a_moogt_automatically(self):
        """It doesn't pauses the moogt until the inactive duration becomes larger than max_inactive_duration"""
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=60,
                             reply_time=timezone.timedelta(days=1),
                             moogt_duration=timezone.timedelta(days=10))
        moogt.set_next_turn_proposition(True)
        moogt.save()

        moogt.func_skip_expired_turns()
        missed_turn: Argument = moogt.arguments.filter(
            type=ArgumentType.MISSED_TURN.name).first()

        moogt.refresh_from_db()

        self.assertFalse(moogt.get_is_paused())
        self.assertEqual(Argument.objects.filter(
            type=ArgumentType.MISSED_TURN.name).count(), 1)
        self.assertEqual(missed_turn.consecutive_expired_turns_count, 2)

    def test_func_skip_expired_turns_with_3_consecutive_expired_turns(self):
        """It creates 3 consecutive expired turns."""
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=46,
                             reply_time=timezone.timedelta(days=1),
                             moogt_duration=timezone.timedelta(days=10))
        moogt.set_next_turn_proposition(True)
        moogt.set_last_posted_by_proposition(False)
        moogt.save()

        moogt.func_skip_expired_turns()
        moogt.refresh_from_db()
        self.assertFalse(moogt.get_next_turn_proposition())
        moogt.func_skip_expired_turns()
        moogt.refresh_from_db()
        self.assertFalse(moogt.get_next_turn_proposition())
        missed_turn: Argument = moogt.arguments.filter(
            type=ArgumentType.MISSED_TURN.name).first()

        moogt.refresh_from_db()

        self.assertFalse(moogt.get_is_paused())
        self.assertEqual(Argument.objects.filter(
            type=ArgumentType.MISSED_TURN.name).count(), 1)
        self.assertEqual(missed_turn.consecutive_expired_turns_count, 1)

    def test_func_skip_expired_turns_should_pause_a_moogt(self):
        """Should pause the moogt if there is inactive duration."""
        started_at = timezone.now() - timezone.timedelta(minutes=9)
        moogt = create_moogt(opposition=True,
                             reply_time=timezone.timedelta(minutes=3),
                             moogt_duration=timezone.timedelta(minutes=30))
        moogt.set_started_at(started_at)
        moogt.set_next_turn_proposition(True)
        moogt.set_latest_argument_added_at(started_at)
        moogt.save()

        moogt.func_skip_expired_turns()
        moogt.set_next_turn_proposition(False)

        missed_turn: Argument = moogt.arguments.filter(
            type=ArgumentType.MISSED_TURN.name).first()

        moogt.refresh_from_db()

        self.assertTrue(moogt.get_is_paused())
        self.assertEqual(Argument.objects.filter(
            type=ArgumentType.MISSED_TURN.name).count(), 1)
        self.assertEqual(missed_turn.consecutive_expired_turns_count, 3)
        self.assertEqual(moogt.statuses.filter(
            status=MoogtStatus.STATUS.auto_paused).count(), 1)
        self.assertEqual(moogt.opposition.notifications.count(), 1)
        self.assertEqual(moogt.proposition.notifications.count(), 1)
        self.assertEqual(
            moogt.opposition.notifications.first().verb, 'auto paused')
        self.assertEqual(
            moogt.proposition.notifications.first().verb, 'auto paused')

    def test_func_get_time_since_last_post(self):
        """It get the time since the last post was made."""
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=3,
                             reply_time=timezone.timedelta(minutes=3),
                             moogt_duration=None)
        result = moogt.func_get_time_since_last_post()
        now = timezone.now()
        self.assertAlmostEqual(result.total_seconds(),
                               (now - moogt.get_latest_argument_added_at()
                                ).total_seconds(),
                               places=3)

    def test_func_get_time_since_last_post_with_expired_moogt(self):
        """If a moogt is expired, it should only include the time till the end time."""
        moogt = create_moogt(started_at_days_ago=3,
                             opposition=True,
                             latest_argument_added_at_hours_ago=48,
                             reply_time=timezone.timedelta(hours=1),
                             moogt_duration=timezone.timedelta(days=2))
        result = moogt.func_get_time_since_last_post()
        self.assertAlmostEqual(result.total_seconds() // 100,
                               (timezone.timedelta(days=1).total_seconds()) // 100)

    def test_func_get_time_since_last_post_with_a_expired_turns(self):
        """
        If the moogt has expired turns, it should return the time since the last argument was posted not
        since the time the expired turn was created. This is since the expired turn is considered as an inactive period
        for the moogt.
        """
        moogt = create_moogt(started_at_days_ago=1,
                             opposition=True,
                             latest_argument_added_at_hours_ago=3,
                             reply_time=timezone.timedelta(hours=1),
                             moogt_duration=timezone.timedelta(days=2))
        moogt.arguments.create(
            type=ArgumentType.MISSED_TURN.name, consecutive_expired_turns_count=2)
        result = moogt.func_get_time_since_last_post()
        self.assertAlmostEqual(result.total_seconds(),
                               (timezone.now() - (moogt.get_latest_argument_added_at() -
                                                  (2 * moogt.get_idle_timeout_duration()))).total_seconds(),
                               places=3)

    def test_func_get_time_since_last_post_with_resumed_at_earlier_than_latest_argument_added_at(self):
        """
        The time since last post should be calculated starting from latest_argument_added_at, if it is
        greater than resumed_at
        """
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=1,
                             reply_time=timezone.timedelta(minutes=3),
                             moogt_duration=None)
        now = timezone.now()
        moogt.set_resumed_at(now - timezone.timedelta(hours=3))
        moogt.save()

        result = moogt.func_get_time_since_last_post()
        self.assertAlmostEqual(result.total_seconds(),
                               (now - moogt.get_latest_argument_added_at()
                                ).total_seconds(),
                               places=1)

    def test_func_ended_by_where_end_has_not_been_requested(self):
        """
        func_ended_by() should return None if end has not been requested
        """
        moogt = create_moogt()
        self.assertIsNone(moogt.func_ended_by())

    def test_func_ended_by_where_end_has_been_requested_by_proposition(self):
        """
        func_ended_by() should return the proposition of the moogt
        """
        moogt = create_moogt(opposition=True)
        moogt.set_end_requested(True)
        moogt.set_end_requested_by_proposition(True)
        self.assertEqual(moogt.func_ended_by(), moogt.get_proposition())

    def test_func_ended_by_where_end_has_been_requested_by_opposition(self):
        """
        func_ended_by() should return the opposition of the moogt
        """
        moogt = create_moogt(opposition=True)
        moogt.set_end_requested(True)
        moogt.set_end_requested_by_proposition(False)
        self.assertEqual(moogt.func_ended_by(), moogt.get_opposition())

    def test_func_end_status_where_end_has_not_been_requested(self):
        """
        func_end_status() should return None
        """
        moogt = create_moogt()
        self.assertIsNone(moogt.func_end_status())

    def test_func_end_status_where_end_has_not_been_requested(self):
        """
        func_end_status() should return None
        """
        moogt = create_moogt()
        self.assertIsNone(moogt.func_end_status())

    def test_func_end_status_where_end_has_been_requested(self):
        """
        func_end_status() should return the end status
        """
        moogt = create_moogt()
        moogt.set_end_requested(True)
        moogt.set_end_request_status(MoogtEndStatus.CNCD.name)
        self.assertEqual(moogt.func_end_status(), MoogtEndStatus.CNCD.value)
        moogt.set_end_request_status(MoogtEndStatus.DSGR.name)
        self.assertEqual(moogt.func_end_status(), MoogtEndStatus.DSGR.value)

    def test_func_start_with_a_moogt_that_has_not_started(self):
        """func_start() should set appropriate values for a moogt"""
        moogt = create_moogt()
        user = MoogtMedaUser(username='testusername')
        user.save()
        moogt.func_start(user)
        self.assertEqual(moogt.get_opposition(), user)
        now = timezone.now().replace(second=0, microsecond=0)
        self.assertEqual(moogt.get_started_at().replace(second=0, microsecond=0),
                         now)
        self.assertEqual(moogt.get_latest_argument_added_at().replace(second=0, microsecond=0),
                         now)

    def test_func_start_with_a_moogt_that_has_started(self):
        """func_start() should raise a ValidationError"""
        moogt = create_moogt(started_at_days_ago=1, opposition=True)
        self.assertRaises(ValidationError, moogt.func_start, None)

    def test_func_ended_by_where_end_has_been_requested_by_opposition(self):
        """
        func_ended_by() should return the opposition of the moogt
        """
        moogt = create_moogt(opposition=True)
        moogt.set_end_requested(True)
        moogt.set_end_requested_by_proposition(False)
        self.assertEqual(moogt.func_ended_by(), moogt.get_opposition())

    def test_func_pause_moogt(self):
        """
        func_pause_moogt should return the time the moogt got paused
        """
        user = MoogtMedaUser(username='testusername')

        moogt = Moogt(proposition=user)
        self.assertEqual(moogt.func_pause_moogt(user), moogt.get_paused_at())

    def test_func_resume_moogt(self):
        """
        func_resume_moogt should return the time the moogt got resumed
        """
        user = MoogtMedaUser(username='testusername')
        now = timezone.now().replace(second=0, microsecond=0)

        moogt = Moogt(proposition=user, is_paused=True, paused_at=now - datetime.timedelta(days=2),
                      latest_argument_added_at=now - datetime.timedelta(days=3))
        self.assertEqual(moogt.func_resume_moogt(user), moogt.get_resumed_at())

    def test_func_resume_moogt_if_not_paused(self):
        """
        func_resume_moogt should return false if the moogt is not paused
        """
        user = MoogtMedaUser(username='testusername')
        user.save()

        moogt = Moogt(proposition=user, is_paused=False)
        self.assertEqual(moogt.func_resume_moogt(user), False)

    def test_func_resume_moogt_timer_should_be_set_back(self):
        """
        func_resume_moogt should set the timer to the value it had when paused
        """
        user = MoogtMedaUser(username='testusername')
        user.save()
        now = timezone.now().replace(second=0, microsecond=0)

        moogt = Moogt(proposition=user, idle_timeout_duration=datetime.timedelta(days=3),
                      started_at=now - datetime.timedelta(days=4),
                      is_paused=True, paused_at=now - datetime.timedelta(days=2),
                      latest_argument_added_at=now - datetime.timedelta(days=3))
        time_left_on_timer_before_paused = (
            moogt.get_latest_argument_added_at() + moogt.get_idle_timeout_duration()) - moogt.get_paused_at()
        moogt.func_resume_moogt(user)

        self.assertEqual(moogt.func_idle_timer_expire_time_remaining(
        ).min, time_left_on_timer_before_paused.min)

    def test_func_create_expired_turn_argument(self):
        """
        Properly checks if expired turns exists, i.e., expired turn immediately before now.
        """
        user = create_user('test_user', 'pass123')
        now = timezone.now().replace(second=0, microsecond=0)

        moogt = Moogt(proposition=user,
                      idle_timeout_duration=datetime.timedelta(days=3),
                      started_at=now - datetime.timedelta(days=4),
                      is_paused=False,
                      latest_argument_added_at=now - datetime.timedelta(days=3))
        moogt.save()

        argument = Argument.objects.create(type=ArgumentType.MISSED_TURN.name,
                                           moogt=moogt,
                                           created_at=timezone.now() - datetime.timedelta(hours=1))

        moogt.func_create_expired_turn_argument(user, 2)
        argument.refresh_from_db()
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(argument.consecutive_expired_turns_count, 2)

    def test_func_create_expired_turn_argument_creates_a_new_argument(self):
        """
        Creates a new expired turn argument if the previous argument is not of type MISSED_TURN.
        """
        user = create_user('test_user', 'pass123')
        now = timezone.now().replace(second=0, microsecond=0)

        moogt = Moogt(proposition=user,
                      idle_timeout_duration=datetime.timedelta(days=3),
                      started_at=now - datetime.timedelta(days=4),
                      is_paused=False,
                      latest_argument_added_at=now - datetime.timedelta(days=3))
        moogt.save()

        argument = Argument.objects.create(type=ArgumentType.MISSED_TURN.name,
                                           moogt=moogt,
                                           created_at=timezone.now() - datetime.timedelta(hours=1))
        Argument.objects.create(type=ArgumentType.NORMAL.name, moogt=moogt)
        moogt.latest_argument_added_at = timezone.now()
        moogt.save()

        moogt.func_create_expired_turn_argument(user, 1)
        argument.refresh_from_db()
        self.assertEqual(Argument.objects.count(), 3)
        self.assertEqual(argument.consecutive_expired_turns_count, 1)

    def test_func_create_expired_turn_argument_for_the_first_time(self):
        """It creates the missed turn argument if the turn expires for the first time."""
        user = create_user('test_user', 'pass123')
        now = timezone.now().replace(second=0, microsecond=0)

        moogt = Moogt(proposition=user,
                      idle_timeout_duration=datetime.timedelta(days=3),
                      started_at=now - datetime.timedelta(days=4),
                      is_paused=False,
                      latest_argument_added_at=now - datetime.timedelta(days=3, seconds=30))
        moogt.save()

        moogt.func_create_expired_turn_argument(user, 1)
        self.assertEqual(Argument.objects.count(), 1)
        missed_turn = Argument.objects.first()
        self.assertEqual(missed_turn.type, ArgumentType.MISSED_TURN.name)

    def test_func_do_not_pause_moogt_if_moogt_is_not_inactive(self):
        """It should not pause the moogt if it does not reach the threshold to pause"""
        user = create_user('test_user', 'pass123')
        now = timezone.now()

        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=2,
                             reply_time=timezone.timedelta(minutes=3),
                             moogt_duration=timezone.timedelta(days=10))
        moogt.save()

        missed_turn: Argument = moogt.arguments.filter(
            created_at__lt=timezone.now()).order_by('-created_at').first()
        moogt.func_skip_expired_turns()

        moogt.refresh_from_db()

        self.assertFalse(moogt.is_paused)

    def test_func_get_max_inactive_duration(self):
        """
        Gets the max inactive duration allowed before a moogt is automatically paused.
        """
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=6,
                             reply_time=timezone.timedelta(minutes=30),
                             moogt_duration=timezone.timedelta(days=8))
        moogt.save()

        result = moogt.func_get_max_inactive_duration()
        self.assertEqual(result, timezone.timedelta(days=2))

    def test_func_get_max_inactive_duration_for_indefinite_moogt(self):
        """
        Gets the max inactive duration allowed for a moogt that has an indefinite duration.
        """
        moogt = create_moogt(started_at_days_ago=4,
                             opposition=True,
                             latest_argument_added_at_hours_ago=6,
                             reply_time=timezone.timedelta(minutes=3),
                             moogt_duration=None)
        moogt.save()

        result = moogt.func_get_max_inactive_duration()
        self.assertEqual(result, timezone.timedelta(hours=3))

    # def test_func_get_last_moogt_item(self):
    #     """
    #     Returns the last Argument in a moogt. It could potentially be null.
    #     """
    #     moogt = create_moogt(started_at_days_ago=4,
    #                          opposition=True,
    #                          latest_argument_added_at_hours_ago=6,
    #                          reply_time=timezone.timedelta(minutes=3),
    #                          moogt_duration=None)
    #     moogt.bundles.create()
    #     last_argument = moogt.func_get_last_argument()
    #     self.assertIsNone(last_argument)

    #     argument = create_argument(user=create_user(
    #         'test', 'pass123'), argument='test arg', moogt=moogt)
    #     last_argument = moogt.func_get_last_argument()
    #     self.assertEqual(argument, last_argument)

    #     moogt.statuses.create()
    #     last_argument = moogt.func_get_last_argument()
    #     self.assertIsNone(last_argument)


class MoogtStatsModelTests(TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.moogt = create_moogt()

    def test_get_share_count_with_no_shares(self):
        """
        If there is no share, it should return 0.
        """
        self.assertEqual(self.moogt.stats.func_get_share_count(), 0)

    def test_one_share_exists(self):
        """
        If one share exists, then it should return 1.
        """
        stats = self.moogt.stats
        ShareStats.objects.create(content_object=stats,
                                  provider=ShareProvider.FACEBOOK.value,
                                  share_count=1)

        self.assertEqual(self.moogt.stats.func_get_share_count(), 1)

    def test_more_than_one_share_exists(self):
        """
        If more than one share exists, it should return a value greater than 1.
        """
        stats = self.moogt.stats
        ShareStats.objects.create(content_object=stats,
                                  provider=ShareProvider.FACEBOOK.value,
                                  share_count=3)

        self.assertEqual(self.moogt.stats.func_get_share_count(), 3)

    def test_func_update_share_count(self):
        """
        If the share stats object doesn't exist, it should create it.
        """
        self.moogt.stats.func_update_share_count(
            ShareProvider.FACEBOOK.name, 0)

        share_stats_count = ShareStats.objects.count()
        self.assertGreater(share_stats_count, 0)
        self.assertEqual(share_stats_count, 1)

        share_stats = ShareStats.objects.first()
        self.assertEqual(share_stats.share_count, 0)

    def test_func_update_share_count(self):
        """
        If the share stats object exists, it should update it.
        """
        self.moogt.stats.func_update_share_count(
            ShareProvider.FACEBOOK.name, 0)
        self.moogt.stats.func_update_share_count(
            ShareProvider.FACEBOOK.name, 1)

        share_stats_count = ShareStats.objects.count()
        self.assertGreater(share_stats_count, 0)
        self.assertEqual(share_stats_count, 1)

        share_stats = ShareStats.objects.first()
        self.assertEqual(share_stats.share_count, 1)
