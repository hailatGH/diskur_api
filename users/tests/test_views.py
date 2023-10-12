import datetime
import os
from unittest.mock import ANY, MagicMock, patch

from avatar.models import Avatar
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from moogtmeda.settings import MEDIA_ROOT

from api.enums import Visibility, ReactionType
from api.tests.tests import create_image
from api.tests.utility import create_user, create_user_and_login, create_moogt_with_user, create_activity, create_view, \
    create_poll, create_reaction_view, create_invitation
from arguments.models import Argument
from meda.models import Score
from meda.tests.test_models import create_moogt
from notifications.models import Notification, NOTIFICATION_TYPES
from polls.models import Poll, PollOption
from users.models import AccountReport, Blocking, MoogtMedaUser, ActivityType
from api.tests.utility import generate_photo_file
from users.tests.factories import BlockingFactory, MoogtMedaUserFactory


def create_user(username, password, first_name=None):
    user = MoogtMedaUser(username=username)
    if first_name:
        user.first_name = first_name
    user.set_password(password)
    user.save()
    return user


class FollowUserAPIViewTests(APITestCase):
    def post(self, pk):
        url = reverse('api:users:follow_user', kwargs={
                      'version': 'v1', 'pk': pk})
        return self.client.post(url)

    def test_success(self):
        followee = create_user("username", "password")
        user = create_user_and_login(self)
        response = self.post(followee.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.followings.count(), 1)
        self.assertEqual(followee.followers.count(), 1)
        self.assertEqual(followee.notifications.count(), 1)
        self.assertEqual(followee.notifications.first().type,
                         NOTIFICATION_TYPES.user_follow)

    def test_unauthenticated_user(self):
        followee = create_user("username", "password")
        response = self.post(followee.id)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(followee.followers.count(), 0)

    def test_non_existing_followee(self):
        user = create_user_and_login(self)
        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(user.followings.count(), 0)

    def test_self_following(self):
        user = create_user_and_login(self)
        response = self.post(user.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(user.followings.count(), 0)

    def test_follow_unfollow(self):
        followee = create_user("username", "password")
        user = create_user_and_login(self)

        response = self.post(followee.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.followings.count(), 1)
        self.assertEqual(followee.followers.count(), 1)
        self.assertEqual(user.priority_conversations.count(), 1)
        self.assertEqual(Notification.objects.filter(
            type=NOTIFICATION_TYPES.user_follow).count(), 1)

        response = self.post(followee.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.followings.count(), 0)
        self.assertEqual(followee.followers.count(), 0)
        self.assertEqual(user.priority_conversations.count(), 0)
        self.assertEqual(Notification.objects.filter(
            type=NOTIFICATION_TYPES.user_follow).count(), 0)

    def test_follow_user_adds_user_to_priority_list(self):
        """
        If a logged in user follows another user the logged in user should have
        the followee in their priority chat listings
        """
        followee = create_user("username", "password")
        user = create_user_and_login(self)

        response = self.post(followee.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.priority_conversations.count(), 1)

    def test_following_blocked_user(self):
        """Should not be able to follow a user you've blocked."""
        followee = create_user("username", "password")
        follower = create_user_and_login(self)

        BlockingFactory.create(user=follower, blocked_user=followee)

        response = self.post(followee.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_following_blocked_by_user(self):
        """Should not be able to follow a user that have blocked you."""
        followee = create_user("username", "password")
        follower = create_user_and_login(self)

        BlockingFactory.create(blocked_user=follower, user=followee)

        response = self.post(followee.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class UserProfileApiViewTests(APITestCase):
    def get(self, user_id, sort_by="date", item_type="moogt", category=None, limit=10, offset=0):
        query_params = "sort_by=" + sort_by \
                       + "&item_type=" + item_type \
                       + "&limit=" + str(limit) \
                       + "&offset=" + str(offset)
        if category:
            query_params += f'&category={category}'
        url = reverse('api:users:profile_user', kwargs={
                      'version': 'v1', 'pk': user_id}) + "?" + query_params
        return self.client.get(url)

    def test_user_success(self):
        """
        Test successfull retrieval of user's profile
        """
        follower = create_user("username", "password")
        user = create_user_and_login(self)
        user.followers.add(follower)
        follower.followings.add(user)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)

        create_activity(user.profile, ActivityType.create_moogt.name, moogt.id)

        response = self.get(user.pk, item_type="moogt")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['is_self_profile'], True)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.id)

    def test_get_profile_views(self):
        """
        Test successfull retrieval of user's profile when items are views
        """
        user = create_user_and_login(self)
        view = create_view(user, "content", Visibility.PUBLIC.name)

        response = self.get(user.pk, item_type="view")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']
                         ['results'][0].get('id'), view.id)

    def test_excluding_draft_views_from_profile(self):
        """
        If a view is a draft view then it should not be included in the search result
        """
        user = create_user_and_login(self)
        view = create_view(user, "content", Visibility.PUBLIC.name)
        view.is_draft = True
        view.save()

        response = self.get(user.pk, item_type="view")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 0)

    def test_get_profile_polls(self):
        """
        Test successfull retrieval of user's profile when items are views
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "title")

        response = self.get(user.pk, item_type="poll")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['results'][0]['id'], poll.id)

    def test_anonymous_user(self):
        """
        Test anonymous user viewing a user's profile
        """
        follower = create_user("username", "password")
        user = create_user("username2", "password")
        user.followers.add(follower)
        follower.followings.add(user)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        create_activity(user.profile, ActivityType.create_moogt.name, moogt.id)

        response = self.get(user.pk, item_type="moogt")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['is_self_profile'], False)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.id)

    def test_no_moogt(self):
        """
        Test viewing a user if user doesn't have any moogt they are participating in
        """
        user = create_user("username", "password")

        response = self.get(user.pk, item_type="moogt")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['items']['results']), 0)

    def test_no_view(self):
        """
        Test user profile is user doesn't have any views created
        """
        user = create_user("username", "password")

        response = self.get(user.pk, item_type="view")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['items']['results']), 0)

    def test_no_poll(self):
        """
        Test user profile if usr doesn't have any polls created
        """
        user = create_user("username", "password")

        response = self.get(user.pk, item_type="poll")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['items']['results']), 0)

    def test_no_activity(self):
        """
        Test viewing a user with no activity
        """
        user = create_user("username", "password")

        response = self.get(user.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewing_other_people_profile(self):
        """
        Test viewing an authenticated user viewing another person's profile
        """
        viewee = create_user("username", "password")
        moogt = create_moogt_with_user(viewee, started_at_days_ago=1)
        create_activity(
            viewee.profile, ActivityType.create_moogt.name, moogt.id)

        user = create_user_and_login(self)
        viewee.followers.add(user)
        user.followings.add(viewee)

        response = self.get(viewee.pk, item_type="moogt")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['is_self_profile'], False)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.id)

    def test_no_subscribers(self):
        """
        Test viewing a user with no subscribers
        """
        user = create_user_and_login(self)
        response = self.get(user.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_subscriber_count(self):
        """
        Test viewing a user with subscribers
        """
        follower = create_user("username", "password")
        user = create_user_and_login(self)

        user.followers.add(follower)
        follower.followings.add(user)

        response = self.get(user.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_moogt_created_count(self):
        """
        Test viewing the number of moogt's created by a user
        """
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        create_activity(user.profile, ActivityType.create_moogt.name, moogt.id)

        response = self.get(user.pk, item_type="moogt")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['items']['results']), 1)

    def test_non_existent_user(self):
        """
        Test viewing a non existent user
        """
        response = self.get(1)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_date_sorting_moogt(self):
        """
        Test sorting by date for moogts
        """
        user = create_user("username", "password")
        moogt2 = create_moogt_with_user(user, started_at_days_ago=1)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        response = self.get(user.pk, item_type="moogt")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.id)

    def test_sort_moogt_by_popularity(self):
        """Test sorting a moogt based on popularity."""
        user = create_user("username", "password")
        moogt_with_more_followers = create_moogt_with_user(
            user, started_at_days_ago=1)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        follower_user = create_user('follower', 'pass123')
        moogt_with_more_followers.followers.add(follower_user)

        response = self.get(user.pk, item_type="moogt", sort_by='popularity')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['items']['results'][0]['id'], moogt_with_more_followers.id)

    def test_date_sorting_view(self):
        """
        Test sorting by date for views
        """
        user = create_user("username", "password")
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        view2 = create_view(user, "view content 2", Visibility.PUBLIC.name)

        response = self.get(user.pk, item_type="view")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['results'][0]['id'], view2.id)

    def test_sort_by_popularity(self):
        """Sort views by popularity"""
        user = create_user("username", "password")
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        view.stats.applauds.add(user)
        view2 = create_view(user, "view content 2", Visibility.PUBLIC.name)

        response = self.get(user.pk, item_type="view", sort_by='popularity')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['results'][0]['id'], view.id)

    def test_date_sorting_poll(self):
        """
        Test sorting by date for polls
        """
        user = create_user("username", "password")
        poll = create_poll(user, "poll title")
        poll2 = create_poll(user, "poll title 2")

        response = self.get(user.pk, item_type="poll")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['results'][0]['id'], poll2.id)

    def test_trending_sorting_view(self):
        """
        Test sorting by trending for views
        """
        user = create_user_and_login(self)
        view_1 = create_view(user, "view content 1", Visibility.PUBLIC.name)
        view_2 = create_view(user, "view content 2", Visibility.PUBLIC.name)

        for i in range(5):
            user_making_reaction = create_user(
                'test_user' + str(i), 'password')
            create_view(user_making_reaction)
            create_reaction_view(user_making_reaction,
                                 view_2,
                                 'test content',
                                 ReactionType.ENDORSE.name)

        view_1.score.score_last_updated_at = timezone.now(
        ) - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
        view_1.score.maybe_update_score()

        view_2.score.score_last_updated_at = timezone.now(
        ) - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
        view_2.score.maybe_update_score()

        response = self.get(user.pk, sort_by="trending", item_type="view")
        self.assertEqual(response.data['items']
                         ['results'][0].get('id'), view_2.id)

    def test_trending_sorting_poll(self):
        """
        Test sorting by trending for polls
        """
        user = create_user_and_login(self)
        poll_1 = create_poll(user, "poll title")
        poll_2 = create_poll(user, "poll title2")

        poll_2.options.first().votes.add(user)
        poll_1 = Poll.objects.get(pk=poll_1.id)
        poll_2 = Poll.objects.get(pk=poll_2.id)

        # Update the score of a poll
        poll_1.score.score_last_updated_at = timezone.now(
        ) - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
        poll_1.score.maybe_update_score()

        poll_2.score.score_last_updated_at = timezone.now(
        ) - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
        poll_2.score.maybe_update_score()
        response = self.get(user.pk, sort_by="popularity", item_type="poll")
        self.assertEqual(response.data['items']
                         ['results'][0].get('id'), poll_2.id)

    def test_moogt_pagination(self):
        """
        Test pagination of moogts
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        moogt2 = create_moogt_with_user(user, started_at_days_ago=1)

        response = self.get(user.pk, sort_by="date",
                            item_type="moogt", limit=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['items']["next"] is None)

    def test_non_started_moogt(self):
        """
        Non started moogts should not be included in a users profile
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user)

        response = self.get(user.pk, sort_by="date", item_type="moogt")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 0)

    def test_live_moogts_category(self):
        """
        Get Live moogts for a user's profile
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        ended_moogt = create_moogt_with_user(user, started_at_days_ago=1)
        ended_moogt.set_has_ended(True)
        ended_moogt.save()

        response = self.get(user.pk, item_type='moogt', category='live')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.pk)

    def test_premiering_moogts(self):
        """
        Premiering moogts should be included in a users profile
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user)
        moogt.is_premiering = True
        moogt.premiering_date = timezone.now() + datetime.timedelta(days=1)
        moogt.save()

        response = self.get(user.pk, item_type="moogt", category='premiering')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.pk)

    def test_ended_moogt_category(self):
        """You should only get an ended moogt in ended category."""
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        moogt.set_has_ended(True)
        moogt.save()

        response = self.get(user.pk, item_type="moogt", category='ended')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.pk)

    def test_paused_moogt_category(self):
        """You should only get paused moogt in paused category."""
        user = create_user_and_login(self)
        create_moogt_with_user(user, started_at_days_ago=1)
        moogt = create_moogt_with_user(user, started_at_days_ago=1)
        moogt.func_pause_moogt(user)
        moogt.save()

        response = self.get(user.pk, item_type="moogt", category='paused')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], moogt.pk)

    def test_views_normal_views_category(self):
        """Get only normal views for a profile"""
        user = create_user_and_login(self)
        view_1 = create_view(user, "view content 1", Visibility.PUBLIC.name)
        reaction_view = create_view(user, "", Visibility.PUBLIC.name)
        reaction_view.parent_view = view_1
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get(user.pk, item_type="view", category='view')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], view_1.id)

    def test_reaction_views(self):
        """Get reaction views for a profile."""
        user = create_user_and_login(self)
        view_1 = create_view(user, "view content 1", Visibility.PUBLIC.name)
        reaction_view = create_view(
            user, "reaction view", Visibility.PUBLIC.name)
        reaction_view.parent_view = view_1
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get(user.pk, item_type="view",
                            category='reaction_view')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']
                         ['results'][0]['id'], reaction_view.id)

    def test_reactions(self):
        """These are one time reactions and they have their own category."""
        user = create_user_and_login(self)
        view_1 = create_view(user, "view content 1", Visibility.PUBLIC.name)
        reaction_view = create_view(user, None, Visibility.PUBLIC.name)
        reaction_view.parent_view = view_1
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get(user.pk, item_type="view", category='reaction')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']['count'], 1)
        self.assertEqual(response.data['items']
                         ['results'][0]['id'], reaction_view.id)

    def test_poll_pagination(self):
        """
        Test pagination of views
        """
        user = create_user_and_login(self)
        poll_1 = create_poll(user, "poll title")
        poll_2 = create_poll(user, "poll title2")

        response = self.get(user.pk, sort_by="date", item_type="poll", limit=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['items']["next"])

    def test_poll_live_poll_category(self):
        """
        Get live polls for a profile
        """
        user = create_user_and_login(self)
        poll_1: Poll = create_poll(user, "poll title")
        poll_1.end_date = timezone.now() - timezone.timedelta(days=1)
        poll_2: Poll = create_poll(user, "poll title2")
        poll_2.end_date = timezone.now() + timezone.timedelta(days=1)
        poll_1.save()
        poll_2.save()

        response = self.get(user.pk, sort_by="date",
                            item_type="poll", category='live')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']["count"], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], poll_2.id)

    def test_closed_polls_category(self):
        """get closed polls for a profile"""
        user = create_user_and_login(self)
        poll_1: Poll = create_poll(user, "poll title")
        poll_1.end_date = timezone.now() - timezone.timedelta(days=1)
        poll_2: Poll = create_poll(user, "poll title2")
        poll_2.end_date = timezone.now() + timezone.timedelta(days=1)
        poll_1.save()
        poll_2.save()

        response = self.get(user.pk, sort_by="date",
                            item_type="poll", category='closed')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items']["count"], 1)
        self.assertEqual(response.data['items']['results'][0]['id'], poll_1.id)

    def test_view_pagination(self):
        """
        Test pagination of polls
        """
        user = create_user_and_login(self)
        view_1 = create_view(user, "view content 1", Visibility.PUBLIC.name)
        view_2 = create_view(user, "view content 2", Visibility.PUBLIC.name)

        response = self.get(user.pk, sort_by="date", item_type="view", limit=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['items']["next"] == None)

    def test_get_arguments_of_profile(self):
        """Get the arguments of a user profile."""
        user = create_user_and_login(self)
        moogt = create_moogt()
        Argument.objects.create(user=user, moogt=moogt,
                                argument='test argument')
        response = self.get(user.pk, item_type='argument', limit=1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['items']['results'][0]['argument'], 'test argument')

    def test_get_argument_stats_properly(self):
        """Get's the stats of the argument properly."""
        user = create_user_and_login(self)
        moogt = create_moogt()
        argument = Argument.objects.create(
            user=user, moogt=moogt, argument='test argument')
        argument.stats.applauds.add(user)
        response = self.get(user.pk, item_type='argument', limit=1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['items']['results'][0]['stats']['applaud']['count'], 1)


class GetProfileItemsCountApiViewTests(APITestCase):
    def get(self, user_id, search_term=None):
        url = reverse('api:users:profile_items_count',
                      kwargs={'version': 'v1', 'pk': user_id})
        if search_term:
            url += f'?q={search_term}'
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """Should get a not authorized response for non authenticated user."""
        self.client.logout()
        response = self.get(self.user.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_user(self):
        """If the user with the given pk does not exist, it should respond with a not found response."""
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_started_moogt_is_not_counted(self):
        """A moogt that's not started should not be counted."""
        moogt = create_moogt()
        moogt.set_proposition(self.user)
        moogt.set_opposition(None)
        moogt.save()

        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 0)

    def test_gets_moogts_count(self):
        """A moogt that's started should be counted."""
        moogt = create_moogt()
        moogt.set_proposition(self.user)
        moogt.set_opposition(create_user('opposition', 'pass123'))
        moogt.started_at = timezone.now()
        moogt.save()
        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 1)

        # Paused moogt should be included in the count
        moogt.func_pause_moogt(self.user)
        moogt.save()
        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 1)

        # Ended moogt should be included in the count
        moogt.set_has_ended(True)
        moogt.save()
        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 1)

        # Deleted moogt should not be included in the count
        moogt.delete()
        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 0)

    def test_gets_only_a_users_moogts(self):
        """Should only get moogts created by a user."""
        moogt = create_moogt()
        moogt.set_proposition(create_user('proposition', 'pass123'))
        moogt.set_opposition(create_user('opposition', 'pass123'))
        moogt.started_at = timezone.now()
        moogt.save()
        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 0)

    def test_get_premiering_moogts(self):
        """Should include premiering moogts as well."""
        moogt = create_moogt()
        moogt.set_proposition(self.user)
        moogt.set_opposition(create_user('opposition', 'pass123'))
        moogt.is_premiering = True
        moogt.premiering_date = timezone.now() + timezone.timedelta(days=3)
        moogt.save()
        response = self.get(self.user.id)
        self.assertEqual(response.data['moogts_count'], 1)

    def test_get_views_created_by_user(self):
        """Should include count of views created by user."""
        create_view(self.user)
        response = self.get(self.user.id)
        self.assertEqual(response.data['views_count'], 1)

    def test_should_only_get_views_created_by_user(self):
        """Should not include count of views created by other users."""
        create_view(create_user('mgtruser', 'pass123'))
        response = self.get(self.user.id)
        self.assertEqual(response.data['views_count'], 0)

    def test_should_include_polls(self):
        """should include count of polls created by user."""
        create_poll(self.user, 'test poll')
        response = self.get(self.user.id)
        self.assertEqual(response.data['polls_count'], 1)

    def test_should_only_get_polls_created_by_user(self):
        """Polls created by other users should not be included."""
        create_poll(create_user('mgtruser', 'pass123'), 'test poll')
        response = self.get(self.user.id)
        self.assertEqual(response.data['polls_count'], 0)

    def test_should_get_arguments_count(self):
        """Should include count of arguments created by a profile."""
        Argument.objects.create(
            user=self.user, argument='test argument', moogt=create_moogt())
        response = self.get(self.user.id)
        self.assertEqual(response.data['arguments_count'], 1)

    def test_should_include_only_normal_argument(self):
        """Should include only normal arguments created by a profile."""
        moogt = create_moogt(0)
        Argument.objects.create(
            user=self.user, argument='test argument', moogt=moogt)

        response = self.get(self.user.id)
        self.assertEqual(response.data['arguments_count'], 1)

    def test_should_search_moogts_by_using_term(self):
        """Should filter moogts based on search term."""
        moogt = create_moogt(resolution='test moogt')
        moogt.set_proposition(self.user)
        moogt.set_opposition(create_user('opposition', 'pass123'))
        moogt.started_at = timezone.now()
        moogt.save()

        response = self.get(self.user.id, 'xyz')
        self.assertEqual(response.data['moogts_count'], 0)

        response = self.get(self.user.id, 'test')
        self.assertEqual(response.data['moogts_count'], 1)

    def test_should_search_views_by_using_search_term(self):
        """Should filter views based on search term."""
        create_view(self.user, content='test view')

        response = self.get(self.user.id, 'xyz')
        self.assertEqual(response.data['views_count'], 0)

        response = self.get(self.user.id, 'test')
        self.assertEqual(response.data['views_count'], 1)

    def test_should_search_polls_by_using_search_term(self):
        """Should filter polls based on search term."""
        poll = create_poll(self.user, 'test poll')
        PollOption.objects.create(poll=poll, content='abc')
        PollOption.objects.create(poll=poll, content='def')

        response = self.get(self.user.id, 'xyz')
        self.assertEqual(response.data['polls_count'], 0)

        response = self.get(self.user.id, 'test')
        self.assertEqual(response.data['polls_count'], 1)

        response = self.get(self.user.id, 'abc')
        self.assertEqual(response.data['polls_count'], 1)

    def test_should_search_arguments_by_using_search_term(self):
        """Should filter arguments based on search term."""
        Argument.objects.create(
            user=self.user, argument='test argument', moogt=create_moogt())

        response = self.get(self.user.id, 'xyz')
        self.assertEqual(response.data['arguments_count'], 0)

        response = self.get(self.user.id, 'test')
        self.assertEqual(response.data['arguments_count'], 1)


class EditProfileApiViewTest(APITestCase):
    def post(self, body, format='json'):
        url = reverse('api:users:edit_user', kwargs={'version': 'v1'})
        return self.client.post(url, body, format=format)

    def test_edit_first_name(self):
        """
        Test successfully update first name
        """
        user = create_user_and_login(self)
        response = self.post({'first_name': 'firstname'})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.first_name, 'firstname')

    def test_edit_last_name(self):
        """
        Test successfully update first name
        """
        user = create_user_and_login(self)
        response = self.post({'last_name': 'lastname'})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.last_name, 'lastname')

    def test_edit_username(self):
        """
        Test successfully update username
        """
        user = create_user_and_login(self)
        response = self.post({'username': 'test_user_name'})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.username, 'test_user_name')

    def test_edit_bio(self):
        """
        Test successfully update bio
        """
        user = create_user_and_login(self)
        response = self.post(
            {'bio': 'test bio', 'profile': {'bio': 'test profile bio'}})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.bio, 'test bio')
        self.assertEqual(user.profile.bio, 'test profile bio')

    def test_edit_quote(self):
        """
        Test successfully update quote
        """
        user = create_user_and_login(self)
        response = self.post({'quote': 'test quote', 'profile': {
                             'quote': 'test profile quote'}})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.quote, 'test quote')
        self.assertEqual(user.profile.quote, 'test profile quote')

    def test_edit_both_bio_and_quote(self):
        """Test successfully update both bio and quote at the same time"""
        user = create_user_and_login(self)

        response1 = self.post(
            {'bio': 'test bio', 'profile': {'bio': 'test profile bio'}})

        response2 = self.post({'quote': 'test quote', 'profile': {
            'quote': 'test profile quote'}})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(user.profile.bio, 'test profile bio')
        self.assertEqual(user.profile.quote, 'test profile quote')

    def test_edit_cover_image(self):
        """
        Test successfully update cover image
        """
        user = create_user_and_login(self)

        image = create_image(None, 'cover_image.png')
        file = SimpleUploadedFile('test_cover_image.png', image.getvalue())

        response = self.post({'cover': file}, format="multipart")
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'test_cover_image')

    def test_edit_taken_user_name(self):
        """
        If a username is taken then editing it to the taken username
        must fail
        """
        user_1 = create_user("test_username", "password")
        user = create_user_and_login(self)

        response = self.post({'username': 'test_username'})
        user = MoogtMedaUser.objects.get(pk=user.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotEqual(user.username, 'test_username')


class UploadProfilePhotoApiViewTests(APITestCase):
    def tearDown(self) -> None:
        if os.path.exists(MEDIA_ROOT):
            for filename in os.listdir(MEDIA_ROOT):
                file_path = os.path.join(MEDIA_ROOT, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except:
                    pass

    def post(self, body=None):
        url = reverse('api:users:upload_profile_photo',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_upload_a_profile_picture(self):
        """Upload a profile photo to the endpoint."""

        profile_photo = generate_photo_file(width=200, height=200)

        data = {
            'profile_photo': profile_photo
        }

        response = self.post(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data['profile']['profile_photo'])

    def test_upload_a_profile_picture_with_different_ratio(self):
        "Tests the image if the width and height of the image os equal or the ratio must be 1"

        profile_photo = generate_photo_file()

        data = {
            'profile_photo': profile_photo
        }

        response = self.post(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_cover_photo(self):
        """Upload a cover photo to the endpoint."""
        cover = generate_photo_file(width=300, height=100)

        data = {
            'cover_photo': cover
        }

        response = self.post(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_upload_cover_photo(self):
        """Upload a cover photo to the endpoint with different height and width."""
        cover = generate_photo_file(width=600, height=100)

        data = {
            'cover_photo': cover
        }

        response = self.post(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RemoveProfileImagesApiViewTests(APITestCase):
    def post(self, body, format='json'):
        url = reverse('api:users:remove_profile_images',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format=format)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_removing_avatars(self):
        """
        If a user requests to delete avatars response should be successfull
        """
        avatar = Avatar(user=self.user, primary=True)
        avatar.save()
        response = self.post({'avatar': True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Avatar.objects.count(), 0)

    def test_removing_cover(self):
        """
        If a user requests to remove covers response should be successfull
        """
        cover_image = create_image(None, 'cover.png')
        cover_file = SimpleUploadedFile(
            'test_cover.png', cover_image.getvalue())
        self.user.cover = cover_file
        self.user.save()

        response = self.post({'cover': True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cover'], None)

    def test_removing_avatars_with_no_avatars(self):
        """
        If a user requests to remove avatars while not having avatars previously response
        should be successfull
        """
        response = self.post({'avatar': True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Avatar.objects.count(), 0)


class GetUsernamesApiViewTests(APITestCase):
    def setUp(self) -> None:
        create_user_and_login(self, 'account1', 'pass123')
        self.user1 = create_user('user1', 'pass123', first_name='testname')
        self.user2 = create_user('user2', 'pass123')
        self.user3 = create_user('user3', 'pass123')
        self.user4 = create_user('inviter', 'pass123')
        self.user5 = create_user('invitee', 'pass123')

        self.moogt = create_moogt()

        invitation = create_invitation(moogt=self.moogt)
        invitation.set_inviter(self.user4)
        invitation.set_invitee(self.user5)
        invitation.save()

    def get(self, q, exclude=None, moogt=None):
        url = reverse('api:users:get_usernames', kwargs={
                      'version': 'v1'}) + f'?q={q}'
        if exclude:
            url += f'&exclude={exclude}'
        if moogt:
            url += f'&moogt={moogt}'

        return self.client.get(url)

    def test_non_authenticated_user(self):
        """Non authenticated user should get a not authorized response."""
        self.client.logout()
        response = self.get('user1')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_user_with_username(self):
        """Should get a 2xx response for an existing user."""
        response = self.get('user1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_get_user_with_firstname(self):
        """Should return a user searched by first name"""
        response = self.get("test")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.user1.pk)

    def test_get_user_with_firstname_ascending(self):
        """Should return a user searched by first name ascendingly"""
        response = self.get("us")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(response.data['results']
                         [0]['username'], self.user1.username)
        self.assertEqual(response.data['results']
                         [1]['username'], self.user2.username)
        self.assertEqual(response.data['results']
                         [2]['username'], self.user3.username)

    def test_get_user_with_at_sign_initiall(self):
        """Should return a user when searched by adding @ sign initially"""
        response = self.get("@user")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)

    def test_exclude_user(self):
        """If who to exclude is provided in the query param, then that user should be excluded."""
        response = self.get('inv', exclude=self.user4.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_exclude_moogt_users(self):
        """If moogt is provided, it should exclude the invitee and inviter."""
        response = self.get('user', moogt=self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)


class RecommendedAccountsApiViewTest(APITestCase):
    def get(self):
        url = reverse('api:users:recommended_accounts',
                      kwargs={'version': 'v1'})
        return self.client.get(url)

    def test_successfully_list_recommended_accounts(self):
        """
        Test if you can successfully list the recommended accounts
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], user_1.id)

    def test_successfully_sort_people_based_on_popularity(self):
        """
        Test if listed recommended accounts are sorted based on follower
        count descending
        """
        user_1 = create_user("username", "password")
        user_2 = create_user("username2", "password")

        user_2.followers.add(user_1)
        user_1.followings.add(user_2)

        user = create_user_and_login(self)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], user_2.id)
        self.assertEqual(response.data['results'][1]['id'], user_1.id)

    def test_exclude_people_a_user_follows(self):
        """
        Test if listed recommended accounts do not include people a user
        follows
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        user_1.followers.add(user)
        user.followings.add(user_1)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


class UserDetailApiViewTests(APITestCase):
    def get(self, user_id):
        url = reverse('api:users:user_detail', kwargs={
            'version': 'v1', 'pk': user_id})
        return self.client.get(url)

    def test_non_logged_in_user(self):
        """Non authorized user should be able to access profile.
        """
        user = create_user('test_user', 'pass123')
        response = self.get(user.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], user.id)
        self.assertEqual(response.data['username'], user.username)

    def test_user_that_does_not_exist(self):
        """Should respond with a not found response for user that does not exist.
        """
        create_user_and_login(self)
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_if_user_doesnt_have_avatar(self):
        """
        If a user does not have an avatar response should include none as the url of the avatar
        """
        user = create_user_and_login(self)

        response = self.get(user.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['avatar_url'], None)

    def test_should_indicate_blocking_status(self):
        """Should indicate whether user is blocking the other user or is being blocked by the other user."""
        user = create_user_and_login(self)
        blocked_user = MoogtMedaUserFactory.create()
        BlockingFactory.create(user=user, blocked_user=blocked_user)

        response = self.get(blocked_user.id)
        self.assertIsNotNone(response.data['is_blocking'])
        self.assertIsNotNone(response.data['is_blocked'])
        self.assertTrue(response.data['is_blocking'])
        self.assertFalse(response.data['is_blocked'])


class GetSubscriptionInfoTests(APITestCase):
    def get(self, subscribed_only='false'):
        query_params = "?subscribed_only=" + str(subscribed_only)
        url = reverse('api:users:subscription_accounts',
                      kwargs={'version': 'v1'}) + query_params
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self, 'account1', 'pass123')

        # this user follows logged in user and has no followers
        self.follower = create_user("follower", 'pass123')
        # logged in user follows this user
        self.followed = create_user("followee", 'pass123')

    def test_successfully_list_subscribers_list(self):
        """
        If a requested user has followers response should include the followers
        """
        self.user.followers.add(self.follower)
        self.follower.followings.add(self.user)

        response = self.get(subscribed_only='false')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.follower.id)

    def test_successfully_list_subscribed_list(self):
        """
        If the logged in user has subscriptions response should include the subscribed accounts
        """
        self.user.followings.add(self.followed)
        self.followed.followers.add(self.user)

        response = self.get(subscribed_only='true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.followed.id)

    def test_no_subscribers_no_subscriptions(self):
        """
        If the logged in user has no subscriptions and no subscribers
        """
        response = self.get(subscribed_only='false')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

        response = self.get(subscribed_only='true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


class RefillWalletApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:users:refill_wallet', kwargs={'version': 'v1'})
        return self.client.post(url, body, content_type='application/json')

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """Non authenticated user, should get a not authorized response."""
        self.client.logout()
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refill_wallet(self):
        """Should refill the wallet of the user."""
        wallet_credit = self.user.wallet.credit

        response = self.post("{\"level1\": 1}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.wallet.refresh_from_db()
        expected_wallet_credit = wallet_credit + 100
        self.assertEqual(self.user.wallet.credit, expected_wallet_credit)
        self.assertEqual(response.data['wallet'], expected_wallet_credit)

        response = self.post("{\"level2\": 2}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.wallet.refresh_from_db()
        expected_wallet_credit = expected_wallet_credit + 1_000 * 2
        self.assertEqual(self.user.wallet.credit, expected_wallet_credit)
        self.assertEqual(response.data['wallet'], expected_wallet_credit)

        response = self.post("{\"level3\": 1}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.wallet.refresh_from_db()
        expected_wallet_credit = expected_wallet_credit + 10_000 * 1
        self.assertEqual(self.user.wallet.credit, expected_wallet_credit)
        self.assertEqual(response.data['wallet'], expected_wallet_credit)

        response = self.post("{\"level4\": 1}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.wallet.refresh_from_db()
        expected_wallet_credit = expected_wallet_credit + 100_000 * 1
        self.assertEqual(self.user.wallet.credit, expected_wallet_credit)
        self.assertEqual(response.data['wallet'], expected_wallet_credit)

        response = self.post("{\"level5\": 1}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.wallet.refresh_from_db()
        expected_wallet_credit = expected_wallet_credit + 1_000_000 * 1
        self.assertEqual(self.user.wallet.credit, expected_wallet_credit)
        self.assertEqual(response.data['wallet'], expected_wallet_credit)

    def test_invalid_data(self):
        """Should get a bad request response if the data is not valid."""
        # Without specifying the level.
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.post({'level5': None})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.post({'level5': 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BlockUserApiViewTests(APITestCase):
    def post(self, user_id):
        url = reverse('api:users:block_user', kwargs={
                      'version': 'v1', 'pk': user_id})
        return self.client.post(url, None)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """Non authenticated user should get a not authorized response.
        """
        self.client.logout()
        user = create_user('user1', 'pass123')
        response = self.post(user.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_user_id(self):
        """Should respond with not found response for a pk that does not exist.
        """
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_trying_to_block_her_or_him_self(self):
        """It should not be possible to block yourself.
        """
        response = self.post(self.user.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_block_and_unblocking_a_user_successfully(self):
        """It should successfully toggle between blocking and unblocking a user.
        """
        blocked_user = create_user('blocked_user', 'pass123')

        response = self.post(blocked_user.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_blocked'])

        blockings = Blocking.objects.all()
        self.assertEqual(blockings.count(), 1)
        blocking = blockings.first()
        self.assertEqual(blocking.user, self.user)
        self.assertEqual(blocking.blocked_user, blocked_user)

        response = self.post(blocked_user.id)
        self.assertFalse(response.data['is_blocked'])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        blockings = Blocking.objects.all()
        self.assertEqual(blockings.count(), 0)

    def test_two_users_blocking_one_another(self):
        """Two users should be able to block one another.
        """
        blocked_user = create_user('blocked_user', 'pass123')
        self.post(blocked_user.id)
        self.client.force_login(blocked_user)

        response = self.post(self.user.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        blockings = Blocking.objects.all()
        self.assertEqual(blockings.count(), 2)
        self.assertEqual(blockings.first().blocked_user, self.user)
        self.assertEqual(blockings.first().user, blocked_user)
        self.assertEqual(blockings.last().user, self.user)
        self.assertEqual(blockings.last().blocked_user, blocked_user)

    def test_unsubscribe_automatically_when_blocking_a_user(self):
        """Should unsubscribe one another automatically after blocking.
        """
        blocked_user = create_user('blocked_user', 'pass123')

        self.user.followings.add(blocked_user)
        blocked_user.followers.add(self.user)

        self.user.followers.add(blocked_user)
        blocked_user.followings.add(self.user)

        response = self.post(blocked_user.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.followings.count(), 0)
        self.assertEqual(self.user.followers.count(), 0)
        self.assertEqual(blocked_user.followings.count(), 0)
        self.assertEqual(blocked_user.followers.count(), 0)

    @patch('moogts.utils.maybe_unfollow_moogts')
    @patch('chat.utils.lock_conversation')
    @patch('chat.utils.unlock_conversation')
    def test_should_call_lock_conversation_when_blocking_a_user(self,  unlock_conversation: MagicMock, lock_conversation: MagicMock, maybe_unfollow_moogts: MagicMock):
        """Should automatically lock/unlock a conversation between the blocker and
        the user being blocked.
        """
        blocked_user = create_user('blocked_user', 'pass123')

        self.post(blocked_user.id)
        lock_conversation.assert_called_once_with(self.user, blocked_user)
        maybe_unfollow_moogts.assert_called_once_with(follower=self.user)

        self.post(blocked_user.id)
        unlock_conversation.assert_called_once_with(self.user, blocked_user)

    @patch('moogts.utils.find_and_quit_moogts')
    def test_should_call_find_and_quit_moogts_when_blocking_a_user(self, find_and_quit_moogts: MagicMock):
        """Should quit moogts that the person quitting the moogt is involved in.
        """
        blocked_user = create_user('blocked_user', 'pass123')

        self.post(blocked_user.id)
        find_and_quit_moogts.assert_called_once_with(self.user, blocked_user)


class BlockedUsersListApiViewTests(APITestCase):
    def get(self):
        url = reverse('api:users:blocked_users_list', kwargs={
                      'version': 'v1'})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.blockings = BlockingFactory.create_batch(size=15, user=self.user)

    def test_non_authenticated_user(self):
        """Non-authenticated user should not be allowed to access the api.
        """
        self.client.logout()
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_should_list_blocked_users(self):
        """Should list blocked users.
        """
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 15)
        self.assertNotEqual(
            response.data['results'][0]['id'], self.blockings[14].blocked_user.id)
        self.assertIsNotNone(response.data['next'])

    def test_should_not_include_non_blocked_users(self):
        """Should not include users that are not included in the list.
        """
        Blocking.objects.all().delete()
        BlockingFactory.create_batch(size=15)

        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

class ReportAccountApiViewTest(APITestCase):
    def post(self, user_id, data=None):
        url = reverse('api:users:report_account', kwargs={'version': 'v1', 'pk': user_id})
        return self.client.post(url, data)
    
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.account = MoogtMedaUserFactory.create()
            
    def test_non_authenticated_user(self):
        """Should get a not-authorized response."""
        self.client.logout()
        response = self.post(self.account.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
    def test_non_existing_user(self):
        """Should response with a not-found response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    @patch('api.mixins.ReportMixin.validate')    
    def test_should_call_validate_method(self, mock_validate: MagicMock):
        """Should call validate to check if the request is valid."""
        self.post(self.account.id)
        mock_validate.assert_called_once_with(created_by=self.account, reported_by=self.user, queryset=ANY)
        
    @patch('api.mixins.ReportMixin.notify_admins')
    def test_notify_admins(self, mock_validate: MagicMock):
        """Should notify admins."""
        self.post(self.account.id, {'link': 'https://moogter.link', 'reason': 'test reason'})
        mock_validate.assert_called_once()
        
    def test_should_create_an_account_report(self):
        """Should create a report for account if the request is valid."""
        response = self.post(self.account.id, {'link': 'https://moogter.link', 'reason': 'test reason'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        account_reports = AccountReport.objects.all()
        
        self.assertEqual(account_reports.count(), 1)
        self.assertEqual(account_reports.first().user, self.account)
        self.assertEqual(account_reports.first().reported_by, self.user)


class RegisterWithPhoneApiViewTest(APITestCase):
    def post(self, data=None):
        url = reverse('api:users:register_with_phone', kwargs={'version': 'v1'})
        return self.client.post(url, data)
    
    def test_unauthenticated_user(self):
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    @patch('users.utils.verify_firebase_user', return_value={'uid': 123})
    def test_with_valid_data(self, magic_mock: MagicMock):
        token = 'test_token'
        response = self.post({
            'first_name': 'Nebiyu',
            'username': 'nebiyu1',
            'phone_number': '+251911111111',
            'firebase_token': token
        })
        
        magic_mock.assert_called_once_with(token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = MoogtMedaUser.objects.first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, 'Nebiyu')
        self.assertEqual(user.username, 'nebiyu1')
        self.assertIsNotNone(user.phone_number)
        self.assertEqual(user.phone_number.phone_number, '+251911111111')
        self.assertEqual(user.phone_number.firebase_uid, '123')