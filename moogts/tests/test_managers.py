from django.test import TestCase
from moogts.models import Moogt

from moogts.tests.factories import MoogtFactory
from users.tests.factories import BlockingFactory, MoogtMedaUserFactory


class MoogtManagerTests(TestCase):
    def setUp(self) -> None:
        self.user = MoogtMedaUserFactory.create()
        self.moogts_without_moderator = MoogtFactory.create_batch(
            size=2, moderator=None)
        self.moogts_with_moderator = MoogtFactory.create_batch(
            size=2
        )
    
    def test_filter_moogts_by_blocked_users_should_not_filter_moogts(self):
        """Should not filter moogts where only one of the moogts is blocked by user.
        """
        propsition = self.moogts_without_moderator[0].get_proposition()
        
        BlockingFactory.create(user=self.user, blocked_user=propsition)
        self.assertEqual(Moogt.objects.filter_moogts_by_blocked_users(self.user).count(), 4)
        
    def test_filter_moogts_by_blocked_users_should_filter_moogts_by_blocked_users(self):
        """Should filter moogts where both of the moogters are blocked by user.
        """
        propsition = self.moogts_without_moderator[0].get_proposition()
        opposition = self.moogts_without_moderator[0].get_opposition()
        
        BlockingFactory.create(user=self.user, blocked_user=propsition)
        BlockingFactory.create(user=self.user, blocked_user=opposition)
        
        self.assertEqual(Moogt.objects.filter_moogts_by_blocked_users(self.user).count(), 3)
        
    
    def test_filter_moogts_by_blocked_users_should_not_filter_moogts_with_moderator(self):
        """If both moogters are blocked by moderator is not blocked, it should not filter
        moogts.
        """
        propsition = self.moogts_with_moderator[0].get_proposition()
        opposition = self.moogts_with_moderator[0].get_opposition()
        
        BlockingFactory.create(user=self.user, blocked_user=propsition)
        BlockingFactory.create(user=self.user, blocked_user=opposition)
        
        self.assertEqual(Moogt.objects.filter_moogts_by_blocked_users(self.user).count(), 4)
        
    def test_filter_moogts_by_blocked_users_should_filter_moogts_with_moderator(self):
        """If all the moogters are blocked, it should filter moogts."""
        propsition = self.moogts_with_moderator[0].get_proposition()
        opposition = self.moogts_with_moderator[0].get_opposition()
        moderator = self.moogts_with_moderator[0].get_moderator()
        
        BlockingFactory.create(user=self.user, blocked_user=propsition)
        BlockingFactory.create(user=self.user, blocked_user=opposition)
        BlockingFactory.create(user=self.user, blocked_user=moderator)
        
        self.assertEqual(Moogt.objects.filter_moogts_by_blocked_users(self.user).count(), 3) 
        
    def test_filter_moogts_by_blocked_users_should_filter_moogts_if_blocked_by_all_moogters(self):
        """Should filter moogts if blocked by all moogters."""
        propsition = self.moogts_without_moderator[0].get_proposition()
        opposition = self.moogts_without_moderator[0].get_opposition()
        
        BlockingFactory.create(blocked_user=self.user, user=propsition)
        BlockingFactory.create(blocked_user=self.user, user=opposition)
       
        self.assertEqual(Moogt.objects.filter_moogts_by_blocked_users(self.user).count(), 3) 

    