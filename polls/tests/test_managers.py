from datetime import datetime, timedelta
from django.test import TestCase
from polls.models import Poll

from polls.tests.factories import PollFactory
from users.tests.factories import BlockingFactory, MoogtMedaUserFactory


class PollManagerTests(TestCase):
    def setUp(self) -> None:
        self.user = MoogtMedaUserFactory.create()
        self.polls = PollFactory.create_batch(size=2, max_duration=timedelta(hours=2), options=[{'content': 'option 1'},
                                                                                                {'content': 'option 2'},
                                                                                                {'content': 'option 3'},
                                                                                                {'content': 'option 4'}],
                                              )

    def test_should_filter_polls_by_blocked_user(self):
        """Should filter polls created by a blocked user.
        """
        blocked_user = self.polls[0].user
        
        BlockingFactory.create(user=self.user, blocked_user=blocked_user)
        
        polls = Poll.objects.filter_poll_by_blocked_user(self.user)
        self.assertEqual(polls.count(), 1)
        
    def test_should_filter_polls_by_blocker_users(self):
        """Should filter polls created by people that have blocked you.
        """
        blocker_user = self.polls[0].user
        
        BlockingFactory.create(user=blocker_user, blocked_user=self.user)
        polls = Poll.objects.filter_poll_by_blocked_user(self.user)
        self.assertEqual(polls.count(), 1)

