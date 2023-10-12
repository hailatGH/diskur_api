from django.test import TestCase
from moogts.models import MoogtStatus
from moogts.tests.factories import MoogtFactory
from moogts.utils import find_and_quit_moogts, maybe_unfollow_moogts

from users.tests.factories import BlockingFactory, MoogtMedaUserFactory


class UtilsTests(TestCase):
    def setUp(self) -> None:
        self.user = MoogtMedaUserFactory()
        self.opponent = MoogtMedaUserFactory()
        self.blocker = MoogtMedaUserFactory()
        
        self.moogts_with_opponent = MoogtFactory.create_batch(size=2, proposition=self.user, opposition=self.opponent)
        self.moogts = MoogtFactory.create_batch(size=2, proposition=self.user)
        
    def test_quit_moogts_should_update_all_moogts_between_user_and_opponent(self):
        """The quit_moogt func should find update the quit_by field of the moogts.
        """
        find_and_quit_moogts(self.user, self.opponent)
        
        self.moogts_with_opponent[0].refresh_from_db()
        self.moogts_with_opponent[1].refresh_from_db()
        self.assertEqual(self.moogts_with_opponent[0].quit_by, self.user)
        self.assertEqual(self.moogts_with_opponent[1].quit_by, self.user)
        
        self.moogts[0].refresh_from_db()
        self.moogts[1].refresh_from_db()
        self.assertIsNone(self.moogts[0].quit_by)
        self.assertIsNone(self.moogts[1].quit_by)
        
    def test_quit_moogts_should_create_broke_off_status(self):
        """Should create a moogt status with broke off status.
        """
        find_and_quit_moogts(self.user, self.opponent)

        self.assertEqual(self.moogts_with_opponent[0].statuses.count(), 1)
        self.assertEqual(self.moogts_with_opponent[0].statuses.first().status, MoogtStatus.STATUS.broke_off)
        self.assertEqual(self.moogts_with_opponent[1].statuses.count(), 1)
        self.assertEqual(self.moogts_with_opponent[1].statuses.first().status, MoogtStatus.STATUS.broke_off)
        
        self.assertEqual(self.moogts[0].statuses.count(), 0)
        self.assertEqual(self.moogts[1].statuses.count(), 0)
        
    def test_quit_moogts_should_update_next_turn_proposition_on_moogt(self):
        """Should update next_turn_proposition on a moogt when someone quits a moogt.
        """
        self.assertTrue(self.moogts_with_opponent[0].next_turn_proposition)
        
        find_and_quit_moogts(self.user, self.opponent)
        
        self.moogts_with_opponent[0].refresh_from_db()
        self.moogts_with_opponent[1].refresh_from_db()
        
        self.assertFalse(self.moogts_with_opponent[0].next_turn_proposition)
        self.assertFalse(self.moogts_with_opponent[1].next_turn_proposition)
        
    def test_maybe_unfollow_moogts_with_no_blocking(self):
        """Should not unfollow moogts you are following if you've not blocked anyone.
        """
        self.blocker.following_moogts.add(self.moogts[0])
        
        maybe_unfollow_moogts(self.blocker)
        
        self.assertEqual(self.blocker.following_moogts.count(), 1)
        
    def test_maybe_unfollow_moogts_with_blocking(self):
        """Should unfollow moogts that you are following if you've blocked every participant."""
        moogt = self.moogts[0]
        moogt.set_moderator(None)
        moogt.save()
        
        BlockingFactory.create(user=self.blocker, blocked_user=moogt.get_proposition())
        BlockingFactory.create(user=self.blocker, blocked_user=moogt.get_opposition())

        self.blocker.following_moogts.add(moogt)
        
        maybe_unfollow_moogts(self.blocker)
        
        self.assertEqual(self.blocker.following_moogts.count(), 0)
        
    def test_maybe_unfollow_moogts_with_moderator_and_blocking(self):
        """Should unfollow moogts with moderator if you've blocked every participant."""
        moogt = self.moogts[0]
        
        self.blocker.following_moogts.add(moogt)
        
        BlockingFactory.create(user=self.blocker, blocked_user=moogt.get_moderator())
        
        maybe_unfollow_moogts(self.blocker)
        
        self.assertEqual(self.blocker.following_moogts.count(), 1)
        
        BlockingFactory.create(user=self.blocker, blocked_user=moogt.get_proposition())
        BlockingFactory.create(user=self.blocker, blocked_user=moogt.get_opposition())
        
        maybe_unfollow_moogts(self.blocker)
        self.assertEqual(self.blocker.following_moogts.count(), 0)
        
    def test_maybe_unfollow_moogts_where_user_is_blocked_by_participants(self):
        """Should unfollow moogts if you have been blocked by every participant."""
        moogt = self.moogts[0]
        moogt.set_moderator(None)
        moogt.save()
        
        self.blocker.following_moogts.add(moogt)
        
        BlockingFactory.create(blocked_user=self.blocker, user=moogt.get_proposition())
        BlockingFactory.create(blocked_user=self.blocker, user=moogt.get_opposition())
        
        maybe_unfollow_moogts(self.blocker)
        
        self.assertEqual(self.blocker.following_moogts.count(), 0)
        
    def test_maybe_unfollow_moogts_with_moderator_where_user_is_blocked_by_participants(self):
        """Should unfollow moogts with moderator user if you have been blocked by every participant."""
        moogt = self.moogts[0]
        self.blocker.following_moogts.add(moogt)
        
        BlockingFactory.create(blocked_user=self.blocker, user=moogt.get_proposition())
        BlockingFactory.create(blocked_user=self.blocker, user=moogt.get_opposition())
        
        maybe_unfollow_moogts(self.blocker)
        
        self.assertEqual(self.blocker.following_moogts.count(), 1)
        
        BlockingFactory.create(blocked_user=self.blocker, user=moogt.get_moderator())
        
        maybe_unfollow_moogts(self.blocker)
        
        self.assertEqual(self.blocker.following_moogts.count(), 0)
        