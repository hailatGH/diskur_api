from django.test import TestCase
from users.models import MoogtMedaUser

from users.tests.factories import MoogtMedaUserFactory, BlockingFactory


class MoogtMedaUserManagerTest(TestCase):
    def setUp(self) -> None:
        self.users = MoogtMedaUserFactory.create_batch(3)
        BlockingFactory.create(user=self.users[0], blocked_user=self.users[1])
        BlockingFactory.create(user=self.users[2], blocked_user=self.users[1])

    def test_get_blocking_status_for_user(self):
        """Should indicate whether or not user is being blocked."""
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[0]).get(pk=self.users[1].pk)
        self.assertTrue(getattr(user, 'is_blocking'))
        self.assertFalse(getattr(user, 'is_blocked'))
        
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[1]
        ).get(pk=self.users[0].pk)
        self.assertTrue(getattr(user, 'is_blocked'))
        self.assertFalse(getattr(user, 'is_blocking'))
        
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[0]).get(pk=self.users[2].pk)
        self.assertFalse(getattr(user, 'is_blocking'))
        self.assertFalse(getattr(user, 'is_blocked'))
        
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[2]).get(pk=self.users[0].pk)
        self.assertFalse(getattr(user, 'is_blocking'))
        self.assertFalse(getattr(user, 'is_blocked'))
        
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[1]).get(pk=self.users[2].pk)
        self.assertFalse(getattr(user, 'is_blocking'))
        self.assertTrue(getattr(user, 'is_blocked'))
        
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[2]).get(pk=self.users[1].pk)
        self.assertTrue(getattr(user, 'is_blocking'))
        self.assertFalse(getattr(user, 'is_blocked'))
        
        user = MoogtMedaUser.objects.annonate_with_blocking_status(
            self.users[0]).get(pk=self.users[0].pk)
        self.assertFalse(getattr(user, 'is_blocking'))
        self.assertFalse(getattr(user, 'is_blocked'))
        
    def test_filter_blocked_users_should_filter_users_you_have_blocked(self):
        """Should filter users that are blocked by you."""
        self.assertEqual(MoogtMedaUser.objects.filter_blocked_users(self.users[0]).count(), 2)
        
    def test_filter_blocked_users_should_filter_users_that_have_blocked_you(self):
        """Should not include users that have blocked you."""
        self.assertEqual(MoogtMedaUser.objects.filter_blocked_users(self.users[1]).count(), 1)
        
    def test_annotate_following_exists_check_if_following_exists(self):
        """Should indicate if following another user or not."""
        follower = self.users[0]
        followee = self.users[1]
        
        follower.followings.add(followee)
        followee.followers.add(follower)
        
        user_being_followed = MoogtMedaUser.objects.annotate_following_exists(follower).get(pk=followee.id)
        user_not_being_followed = MoogtMedaUser.objects.annotate_following_exists(follower).get(pk=self.users[2].id)
        self.assertTrue(getattr(user_being_followed, 'is_following', False))
        self.assertFalse(getattr(user_not_being_followed, 'is_following', True))
