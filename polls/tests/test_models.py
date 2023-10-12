import datetime

from django.utils import timezone
from rest_framework.test import APITestCase

from api.tests.utility import (create_poll, create_user)
from meda.models import Score
from polls.models import Poll


class PollScoreModelTests(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = create_user('test_user', 'test_password')

    def test_can_score_be_updated(self):
        """
        This method should return true if now - score_last_update_at is greater than X,
        where X is a duration we can control
        """
        poll = create_poll(self.user, 'test poll')
        self.assertFalse(poll.score._can_score_be_updated())

        poll.score.score_last_updated_at = timezone.now() - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
        poll.score.save()

        self.assertTrue(poll.score._can_score_be_updated())


class PollModelTests(APITestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = create_user('test_user', 'test_password')

    def test_num_voters_nobody_has_voted(self):
        """
        If nobody has voted on a poll, num_voters func should return 0
        """
        poll = create_poll(user=self.user, title='test poll title')
        self.assertEqual(poll.total_vote, 0)

    def test_num_voters_one_person_has_voted(self):
        """
        If one person has voted on the poll, num_voters func should return 1
        """
        poll = create_poll(user=self.user, title='test poll title with votes')
        first_poll_option = poll.options.first()
        voter = create_user('test_voter_user', 'test_user')
        first_poll_option.votes.add(voter)
        poll = Poll.objects.get(pk=poll.id)
        self.assertEqual(poll.total_vote, 1)


class PollOptionModelTests(APITestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = create_user('test_user', 'test_password')

    def test_win_percentage_nobody_has_voted(self):
        """
        If nobody has voted, each vote should has zero percentage
        """
        poll = create_poll(user=self.user, title='test poll title with votes')
        first_poll_option = poll.options.first()
        self.assertEqual(first_poll_option.win_percentage(), 0)

    def test_win_percentage_one_person_has_voted(self):
        """
        If one person has voted, that poll option should have 100% win percentage
        """
        poll = create_poll(user=self.user, title='test poll title with votes')
        first_poll_option = poll.options.first()
        voter = create_user('test_voter_user', 'test_user')
        first_poll_option.votes.add(voter)

        poll = Poll.objects.get(pk=poll.id)
        first_poll_option = poll.options.first()

        self.assertEqual(first_poll_option.win_percentage(), 100)

    def test_win_percentage_two_people_have_voted(self):
        """
        If two people have voted, the two poll options should have 50% win percentage
        """
        poll = create_poll(user=self.user, title='test poll title with votes')
        first_poll_option = poll.options.first()
        last_poll_option = poll.options.last()

        voter_a = create_user('test_voter_a', 'test_user')
        voter_b = create_user('test_voter_b', 'test_user')

        first_poll_option.votes.add(voter_a)
        last_poll_option.votes.add(voter_b)

        poll = Poll.objects.get(pk=poll.id)
        first_poll_option = poll.options.first()
        last_poll_option = poll.options.last()

        self.assertEqual(first_poll_option.win_percentage(), 50)
        self.assertEqual(last_poll_option.win_percentage(), 50)

    def test_win_percentage_three_people_have_voted(self):
        """
        If three people have voted, the first poll option should have 33% win percentage
        """
        poll = create_poll(user=self.user, title='test poll title with votes')
        first_poll_option = poll.options.first()
        last_poll_option = poll.options.last()

        voter_a = create_user('test_voter_a', 'test_user')
        voter_b = create_user('test_voter_b', 'test_user')
        voter_c = create_user('test_voter_c', 'test_user')

        first_poll_option.votes.add(voter_a)
        last_poll_option.votes.add(voter_b)
        last_poll_option.votes.add(voter_c)

        poll = Poll.objects.get(pk=poll.id)
        first_poll_option = poll.options.first()
        last_poll_option = poll.options.last()

        self.assertEqual(first_poll_option.win_percentage(), 33)
        self.assertEqual(last_poll_option.win_percentage(), 66)
