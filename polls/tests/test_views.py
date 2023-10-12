from datetime import timedelta
from unittest.mock import ANY, MagicMock, patch
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.enums import Visibility
from api.tests.utility import create_poll, create_user, create_comment
from api.tests.utility import create_user_and_login
from notifications.models import NOTIFICATION_TYPES
from polls.models import Poll, PollOption, PollReport
from polls.serializers import PollNotificationSerializer
from polls.tests.factories import PollFactory


class CreatePollViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:polls:create_poll', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_create_successfull_poll(self):
        """
        Create a successfull poll
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"},
                                          {"content": "option 4"}]
                              })

        self.assertEqual(Poll.objects.count(), 1)
        self.assertEqual(PollOption.objects.count(), 4)
        self.assertEqual(PollOption.objects.first().poll, Poll.objects.first())

    def test_create_poll_with_unauthenticated_user(self):
        """
        User tries to create a poll while unauthenticated
        """
        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"},
                                          {"content": "option 4"}]
                              })

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Poll.objects.count(), 0)
        self.assertEqual(PollOption.objects.count(), 0)

    def test_has_no_max_duration(self):
        """
        Poll has no max_duration; poll should not be created
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"},
                                          {"content": "option 4"}]
                              })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_has_no_end_date(self):
        """
        Poll has no end date
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"},
                                          {"content": "option 4"}]
                              })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_has_no_visibility(self):
        """
        Poll has no visibility status
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"},
                                          {"content": "option 4"}]
                              })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Poll.objects.count(), 1)
        self.assertEqual(PollOption.objects.count(), 4)

    def test_has_no_options(self):
        """
        Poll has no options
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name
                              })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Poll.objects.count(), 0)
        self.assertEqual(PollOption.objects.count(), 0)

    def test_has_no_title(self):
        """
        Poll has no title
        """
        user = create_user_and_login(self)

        response = self.post({'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"},
                                          {"content": "option 4"}]
                              })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Poll.objects.count(), 0)
        self.assertEqual(PollOption.objects.count(), 0)

    def test_poll_is_public(self):
        """
        Test if created Poll is public
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"}]
                              })

        self.assertEqual(Poll.objects.count(), 1)
        self.assertEqual(Poll.objects.first().visibility, Visibility.PUBLIC.name)

    def test_poll_option_in_poll(self):
        """
        Test if created poll has options
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"}]
                              })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Poll.objects.count(), 1)
        self.assertEqual(Poll.objects.first().options.count(), 3)

    def test_poll_creator(self):
        """
        Test the if the poll creator is in the poll
        """
        user = create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"}]
                              })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Poll.objects.first().user, user)

    def test_poll_end_date_should_be_set_properly(self):
        """
        The end date of the poll should be set properly based on the max duration value
        provided from the client
        """
        create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 600,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"}]
                              })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        poll = Poll.objects.get(pk=response.data['id'])
        self.assertIsNotNone(poll.start_date)
        self.assertIsNotNone(poll.end_date)
        self.assertEqual(poll.start_date + poll.max_duration, poll.end_date)

    def test_poll_with_invalid_min_duration(self):
        """
        The duration for a poll should not be less than the allowed amount,
        if that's the case the poll should to be created
        """
        create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 60,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"}]
                              })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_invalid_max_duration(self):
        """
        The duration for a poll should not be greater than the allowed amount,
        if that's the case the poll should to be created
        """
        create_user_and_login(self)

        response = self.post({'title': 'poll question',
                              'max_duration': 3000000,
                              'visibility': Visibility.PUBLIC.name,
                              'options': [{"content": "option 1"},
                                          {"content": "option 2"},
                                          {"content": "option 3"}]
                              })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PollDetailApiView(APITestCase):
    def get(self, poll_id):
        url = reverse('api:polls:poll_detail', kwargs={'version': 'v1', 'pk': poll_id})
        return self.client.get(url, format='json')

    def test_detail(self):
        user = create_user_and_login(self)
        poll: Poll = create_poll(user, "poll title")
        poll.options.first().votes.add(user)

        response = self.get(poll.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], poll.id)
        self.assertEqual(response.data['options'][0]['num_of_votes'], 1)
        self.assertEqual(response.data['options'][0]['has_voted'], True)
        self.assertEqual(response.data['can_vote'], False)

    def test_send_poll_closed_notification(self):
        """
        When the poll ends it should send poll closed notification.
        """
        user = create_user_and_login(self)
        poll: Poll = create_poll(user, "poll title")

        response = self.get(poll.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.notifications.count(), 0)

        poll.end_date = timezone.now() - timezone.timedelta(hours=1)
        poll.save()
        self.get(poll.pk)
        self.assertEqual(user.notifications.count(), 1)
        self.assertEqual(user.notifications.first().verb, 'closed')
        self.assertEqual(user.notifications.first().type, NOTIFICATION_TYPES.poll_closed)
        self.assertEqual(user.notifications.first().data['data']['poll'], PollNotificationSerializer(poll).data)

        self.get(poll.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.notifications.count(), 1)


class PollCommentCreateAPITests(APITestCase):
    def post(self, body=None):
        url = reverse('api:polls:comment_poll', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_should_get_not_found_response_for_invalid_or_no_poll_id(self):
        """
        Should respond with a not found response if the poll_id is not provided in the request body,
        or is for a poll that does not exist.
        """
        create_user_and_login(self)

        response = self.post({
            'comment': 'test comment'
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.post({
            'poll_id': 404,
            'comment': 'test comment'
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_successfully_create_comment(self):
        """
        Test if you can successfully comment on Poll
        """
        commenter = create_user_and_login(self)
        user = create_user("username", "password")
        poll: Poll = create_poll(user, "poll title")

        response = self.post({
            'poll_id': poll.id,
            'comment': 'test comment'
        })

        poll.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(poll.comments_count(), 1)
        self.assertEqual(user.notifications.count(), 1)
        self.assertEqual(user.notifications.first().type, NOTIFICATION_TYPES.poll_comment)

    def test_comment_on_owned_poll(self):
        """
        If a user comments on their own poll they should not get notifications
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")

        response = self.post({
            'poll_id': poll.id,
            'comment': 'test comment'
        })

        poll.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(poll.comments_count(), 1)
        self.assertEqual(user.notifications.count(), 0)

    def test_reply_to_comment(self):
        """
        Test if you can successfully reply to a comment on an poll
        """
        commenter = create_user_and_login(self)
        user = create_user("username", "password")
        poll: Poll = create_poll(user, "poll title")

        comment = create_comment(poll, user, "test comment")

        response = self.post({
            'poll_id': poll.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        poll.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(poll.comments_count(), 2)


class ListPollCommentsAPITests(APITestCase):
    def get(self, argument_id, limit=3, offset=0):
        url = reverse('api:polls:list_comment', kwargs={'version': 'v1', 'pk': argument_id}) + '?limit=' + str(
            limit) + '&offset=' + str(offset)
        return self.client.get(url, format='json')

    def reply(self, body=None):
        url = reverse('api:polls:comment_poll', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_list_comments(self):
        """
        Test if you can successfully list all comments of an argument
        """
        user = create_user_and_login(self)

        argument = create_poll(user, "test poll")

        for i in range(5):
            create_comment(argument, user, "test comment")

        response = self.get(argument.id, limit=5)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(response.data['results'][0]['user_id'], user.id)

    def test_reply_to_comment(self):
        """
        Test if you can successfully list replies to comment on an argument
        """
        user = create_user("username", "password")
        commenter = create_user_and_login(self)
        poll = create_poll(user, "test poll")

        comment = create_comment(poll, user, "test comment")

        self.reply({
            'poll_id': poll.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        response = self.get(poll.id, limit=5)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)


class BrowsePollViewAPITests(APITestCase):
    def get(self, trending="false"):
        url = reverse('api:polls:list_poll', kwargs={'version': 'v1'}) + f'?trending={trending}'
        return self.client.get(url)

    def test_no_poll(self):
        """
        When no polls exist there must be no poll objects returned
        """
        create_user_and_login(self)
        response = self.get()
        self.assertEqual(response.data.get('count'), 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_a_poll_exist(self):
        """
        If a poll exists, it should be included in the response.
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('count'), 1)

    def test_a_poll_exist(self):
        """
        If two polls exist, they should be included in the response.
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")
        poll = create_poll(user, "poll title")
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('count'), 2)
        self.assertIsNotNone(response.data['results'][0]['start_date'])
        self.assertIsNotNone(response.data['results'][0]['end_date'])

    def test_unauthenticated_user_poll(self):
        """
        can get a list of views while unauthenticated.
        """
        user = create_user("username", "password")
        poll = create_poll(user, "poll title")

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('count'), 1)

    # This test is failing just because our tests are using SQLite db.
    # Trying to get duration as seconds(or integers) is different depending on the database.
    # Since we're using PostgreSQL this test is commented out.
    # def test_returns_polls_based_on_score(self):
    #     """
    #     If a poll has more engagements compared to other polls, it should appear first
    #     """
    #     user = create_user_and_login(self)
    #     poll_1 = create_poll(user, "poll title")
    #     poll_2 = create_poll(user, "poll title2")
    #
    #     poll_1.options.first().votes.add(user)
    #
    #     # Update the score of a view
    #     poll_1.score.score_last_updated_at = timezone.now() - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
    #     poll_1.score.maybe_update_score()
    #
    #     poll_2.score.score_last_updated_at = timezone.now() - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
    #     poll_2.score.maybe_update_score()
    #
    #     response = self.get(trending='true')
    #     self.assertEqual(response.data.get("results")[0].get("id"), poll_1.id)
    #     self.assertEqual(response.data['results'][0]['stats']['comment']['selected'], False)

    def test_poll_with_comment(self):
        """
        If a poll has comments it should be indicated in the comment_count field
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")
        comment = create_comment(poll, user, "test comment")

        response = self.get()

        self.assertEqual(response.data['results'][0]['id'], poll.pk)
        self.assertEqual(response.data['results'][0]['comment_count'], 1)
        self.assertEqual(response.data['results'][0]['stats']['comment']['selected'], True)


class UpdatePollPublicityStatusViewTest(APITestCase):
    def post(self, body):
        url = reverse('api:polls:update_poll_publicity', kwargs={'version': 'v1'})
        return self.client.post(url, body, format="json")

    def test_successfully_update_poll(self):
        """
        Test successfully update publicity status of a poll
        """

        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")
        response = self.post({"poll_id": poll.id,
                              "visibility": Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["visibility"], Visibility.FOLLOWERS_ONLY.name)

    def test_non_existent_moogt(self):
        """
        Test updating publicity status of a non existent poll
        """
        user = create_user_and_login(self)
        response = self.post({"poll_id": 1,
                              "visibility": Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_status(self):
        """
        Test Updating publicity status with an invalid status
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")

        response = self.post({"poll_id": poll.id,
                              "visibility": "Invalid status"}
                             )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class VotePollAPIViewTests(APITestCase):
    def post(self, poll_option_id, body=None):
        url = reverse('api:polls:vote_poll', kwargs={'pk': poll_option_id, 'version': 'v1'})
        return self.client.post(url, body)

    def test_vote_successfully(self):
        """
        Vote successfully on a poll
        """
        poll_owner = create_user("username1", "password")
        poll = create_poll(poll_owner, "poll title")

        user = create_user_and_login(self)
        option = poll.options.first()
        response = self.post(option.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(option.votes.count(), 1)
        self.assertEqual(response.data['options'][0]['num_of_votes'], 1)
        self.assertEqual(response.data['can_vote'], False)
        self.assertEqual(poll_owner.notifications.count(), 1)
        self.assertEqual(poll_owner.notifications.first().type, NOTIFICATION_TYPES.poll_vote)

    def test_vote_twice(self):
        """
        Vote successfully on a poll
        """

        poll_owner = create_user("username", "password")
        poll = create_poll(poll_owner, "poll title")

        user = create_user_and_login(self)
        option = poll.options.first()
        response = self.post(option.id)
        response = self.post(option.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(option.votes.count(), 1)

    def test_vote_unauthenticated_user(self):
        """
        Vote using unauthenticated user on a poll
        """
        user = create_user("username", "password")
        poll = create_poll(user, "poll title")
        option = poll.options.first()
        response = self.post(option.id)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(option.votes.count(), 0)

    def test_vote_non_existing_poll(self):
        """
        Vote on a non existing poll
        """
        user = create_user_and_login(self)
        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(PollOption.objects.count(), 0)

    def test_vote_non_existing_poll_option(self):
        """
        Vote on a non-existing option
        """
        poll_owner = create_user("username", "password")
        user = create_user_and_login(self)
        poll = create_poll(poll_owner, "poll title")
        response = self.post(5)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_vote_on_owned_poll(self):
        """
        Vote on a poll owned by the creator of the poll
        """
        user = create_user_and_login(self)
        poll = create_poll(user, "poll title")
        option = poll.options.first()
        response = self.post(option.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(option.votes.count(), 0)
        self.assertEqual(user.notifications.count(), 0)

    def test_vote_expired_poll(self):
        """
        Vote on an expired poll
        """
        poll_owner = create_user("username", "password")
        user = create_user_and_login(self)
        poll = create_poll(poll_owner, "poll title", end_date=timezone.now() - timezone.timedelta(days=1))
        option = poll.options.first()
        response = self.post(option.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(option.votes.count(), 0)


class DeletePollApiViewTests(APITestCase):
    def setUp(self): 
        self.user = create_user_and_login(self)
        self.poll = create_poll(self.user, 'test poll')

    def post(self, poll_id):
        url = reverse('api:polls:delete_poll',  kwargs={'pk': poll_id, 'version': 'v1'})
        return self.client.post(url)

    def test_should_poll_that_does_not_exist(self):
        """
        Should respond with a 404 response.
        """
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_authenticated_user(self):
        """
        Should respond with a 401 response.
        """
        self.client.logout()
        response = self.post(self.poll.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_of_a_poll(self):
        """
        Should respond with a 400 response for non owners.
        """
        user = create_user('test_user', 'pass123')
        poll = create_poll(user, 'poll 123')
        response = self.post(poll.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_should_delete_a_poll_successfully(self):
        """
        Should delete a poll successfully and respond with a 200 response.
        """
        response = self.post(self.poll.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        
class ReportPollApiViewTests(APITestCase):
    def post(self, poll_id, data=None):
        url = reverse('api:polls:report_poll', kwargs={'pk': poll_id, 'version': 'v1'})
        return self.client.post(url, data)
    
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.poll = PollFactory.create(max_duration=timedelta(hours=2), options=[{'content': 'option 1'},
                                                                                                {'content': 'option 2'},
                                                                                                {'content': 'option 3'},
                                                                                                {'content': 'option 4'}])
        
    def test_non_authenticated_user(self):
        """Non authenticated user should get a not authorized response."""
        self.client.logout()
        response = self.post(self.poll.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
    def test_non_existing_poll(self):
        """Should get a not found response for a poll that does not exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
    @patch('api.mixins.ReportMixin.validate')
    def test_should_validate_request(self, mock_validate: MagicMock):
        """Should call validate method."""
        self.post(self.poll.id)
        mock_validate.assert_called_once_with(created_by=self.poll.user, 
                                              reported_by=self.user,
                                              queryset=ANY)
        
    @patch('api.mixins.ReportMixin.notify_admins')
    def test_notify_admins(self, mock_validate: MagicMock):
        """Should notify admins."""
        self.post(self.poll.id, {'link': 'https://moogter.link', 'reason': 'test reason'})
        mock_validate.assert_called_once()
        
    def test_should_create_a_poll_report(self):
        """Should create a poll report if the request is valid."""
        response = self.post(self.poll.id, {'link': 'https://moogter.link', 'reason': 'test reason'})
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        poll_reports = PollReport.objects.all()
        
        self.assertEqual(poll_reports.count(), 1)
        self.assertEqual(poll_reports.first().reported_by, self.user)
        self.assertEqual(poll_reports.first().poll, self.poll)