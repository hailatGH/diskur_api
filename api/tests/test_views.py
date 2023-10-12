from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from django_comments.models import CommentFlag
from django_comments_xtd.models import XtdComment, LIKEDIT_FLAG, DISLIKEDIT_FLAG
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from api.enums import Visibility, ReactionType, ViewType
from api.models import TelegramChatToUser
from invitations.models import ModeratorInvitation
from meda.enums import InvitationStatus
from meda.tests.test_models import create_moogt
from moogts.models import Donation, DonationLevel, ReadBy
from notifications.models import NOTIFICATION_TYPES
from users.models import MoogtMedaUser
from views.models import ViewImage, View
from .utility import (create_invitation, create_moogt_with_user, create_poll,
                      create_user, create_reaction_view, create_argument,
                      create_user_and_login, create_view, create_comment)


class SideBarAPIViewTests(APITestCase):
    def get(self):
        url = reverse('api:sidebar_view', kwargs={'version': 'v1'})
        return self.client.get(url)

    def test_success(self):
        """
        If there is an open invitation of a user, subscribers and subscribed 
        it should return the number of their count
        """
        user_1 = create_user("username", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")
        invitation = create_invitation(moogt,
                                       InvitationStatus.PENDING.name,
                                       inviter=moogt.get_proposition())

        user.followers.add(user_1)
        user.followings.add(user_1)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogt_count'], 1)
        self.assertEqual(response.data.get('subscriber_count'), 1)
        self.assertEqual(response.data.get('subscribed_count'), 1)
        self.assertEqual(response.data['open_invitation_count'], 1)

    def test_no_subscribers(self):
        """
        test if there are no subscribers response should return 0 for subscriber_count
        """
        user_1 = create_user("username", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogt_count'], 1)
        self.assertEqual(response.data.get('subscriber_count'), 0)

    def test_no_subscribed(self):
        """
        test if there are no subscribed users response should return 0 for subscribed_count
        """
        user_1 = create_user("username", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogt_count'], 1)
        self.assertEqual(response.data.get('subscribed_count'), 0)

    def test_no_open_invitation(self):
        """
        test if there are no open invitations response should return 0 for open_invitation_count
        """
        user_1 = create_user("username", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")
        invitation = create_invitation(moogt, InvitationStatus.PENDING.name,
                                       inviter=moogt.get_proposition(),
                                       invitee=user_1)

        user.followers.add(user_1)
        user.followings.add(user_1)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogt_count'], 1)
        self.assertEqual(response.data['open_invitation_count'], 0)

    def test_no_moogts_created(self):
        """
        if no moogts created response should return 0 for moogt_count
        """
        user = create_user_and_login(self)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogt_count'], 0)

    def test_non_pending_open_invitation(self):
        """
        test if no
        """
        user_1 = create_user("username", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")
        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       inviter=moogt.get_proposition())

        user.followers.add(user_1)
        user.followings.add(user_1)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogt_count'], 1)
        self.assertEqual(response.data['open_invitation_count'], 0)

    def test_unauthenticated_user(self):
        """
        test if its unauthenticated user tries to access side bar response
        should be unauthorized
        """
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_donated_amount(self):
        """
        Test if the sidebar api view response includes the sum of the donations from all the moogts
        """
        donator = create_user("donator", "password")
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)
        moogt2 = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)

        donation = Donation.objects.create(moogt=moogt, level=DonationLevel.LEVEL_3.name, amount=10,
                                           donation_for_proposition=True, donated_for=proposition,
                                           user=donator)

        donation2 = Donation.objects.create(moogt=moogt, level=DonationLevel.LEVEL_2.name, amount=5,
                                            donation_for_proposition=False, donated_for=opposition,
                                            user=donator)

        donation3 = Donation.objects.create(moogt=moogt2, level=DonationLevel.LEVEL_2.name, amount=5,
                                            donation_for_proposition=True, donated_for=proposition,
                                            user=donator)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['donations_amount'], 15)

    def test_wallet_amount(self):
        """
        Test if the sidebar api view response includes the wallet amount of 
        """
        donator = create_user_and_login(self)
        opposition = create_user("opposition", "password")
        proposition = create_user("proposition", "password")
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)
        moogt2 = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)

        donation = Donation.objects.create(moogt=moogt, level=DonationLevel.LEVEL_3.name,
                                           donation_for_proposition=True, donated_for=proposition,
                                           user=donator)
        donator.wallet.credit = donator.wallet.credit - \
            Donation.get_equivalence_amount(DonationLevel.LEVEL_3.name)

        donation2 = Donation.objects.create(moogt=moogt, level=DonationLevel.LEVEL_2.name,
                                            donation_for_proposition=False, donated_for=opposition,
                                            user=donator)
        donator.wallet.credit = donator.wallet.credit - \
            Donation.get_equivalence_amount(DonationLevel.LEVEL_2.name)

        donation3 = Donation.objects.create(moogt=moogt2, level=DonationLevel.LEVEL_2.name,
                                            donation_for_proposition=True, donated_for=proposition,
                                            user=donator)
        donator.wallet.credit = donator.wallet.credit - \
            Donation.get_equivalence_amount(DonationLevel.LEVEL_3.name)
        donator.wallet.save()

        response = self.get()

        total_donations = Donation.get_equivalence_amount(DonationLevel.LEVEL_3.name) * 2 + \
            Donation.get_equivalence_amount(DonationLevel.LEVEL_2.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['wallet_amount'], 5_000 - total_donations)


class RestAuthRegistrationAPIViewTests(APITestCase):
    def post(self, data):
        url = reverse('api:rest_register')
        return self.client.post(url, data=data)

    def test_success(self):
        """
        test successfull registration and creation of user
        """
        REGISTRATION_DATA = {
            "username": "test_user_name",
            "password1": "testpassword@123",
            "password2": "testpassword@123",
            "first_name": "test_first_name",
            "email": "test_email@gmail.com"
        }

        response = self.post(data=REGISTRATION_DATA)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MoogtMedaUser.objects.count(), 1)
        self.assertEqual(MoogtMedaUser.objects.first().username,
                         REGISTRATION_DATA["username"])
        self.assertEqual(MoogtMedaUser.objects.first(
        ).first_name, REGISTRATION_DATA["first_name"])

    def test_no_first_name(self):
        """
        test if no first name is included then user shall not be created
        """
        REGISTRATION_DATA = {
            "username": "test_user_name",
            "password1": "testpassword@123",
            "password2": "testpassword@123",
            "last_name": "test_last_name",
            "email": "test_email@gmail.com"
        }

        response = self.post(data=REGISTRATION_DATA)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MoogtMedaUser.objects.count(), 0)

    def test_no_email(self):
        """
        test if no email is included then user shall not be created
        """
        REGISTRATION_DATA = {
            "username": "test_user_name",
            "password1": "testpassword@123",
            "password2": "testpassword@123",
            "first_name": "test_first_name",
            "last_name": "test_last_name",
        }

        response = self.post(data=REGISTRATION_DATA)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MoogtMedaUser.objects.count(), 0)


class FeedContentApiViewTests(APITestCase):
    def get(self, limit=3, offset=0):
        url = reverse('api:feed_content', kwargs={
                      'version': 'v1'}) + '?limit=' + str(limit) + '&offset=' + str(offset)
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user("follower user", "password")
        self.follower = create_user_and_login(self)
        self.follow(self.follower, self.user)

    def follow(self, follower, followee):
        follower.followings.add(followee)
        followee.followers.add(follower)

    def test_view_response_contains_necessary_fields(self):
        """
        A view in the response must contain all the required fields by clients.
        """
        view = create_view(self.user, "view content", Visibility.PUBLIC.name)
        response = self.get(5, 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], view.id)
        self.assertEqual(response.data['results'][0]['content'], view.content)
        self.assertIsNotNone(response.data['results'][0]['user_id'])
        self.assertIsNotNone(response.data['results'][0]['stats'])

    def test_moogt_response_contains_necessary_fields(self):
        """
        A moogt in the response must contain all the required fields by clients.
        """
        moogt = create_moogt_with_user(
            self.user, "moogt content", started_at_days_ago=1)
        read_by = ReadBy.objects.create(
            user=self.follower, moogt=moogt, latest_read_at=timezone.now())

        response = self.get(5, 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], moogt.id)
        self.assertEqual(response.data['results']
                         [0]['resolution'], moogt.resolution)
        self.assertIsNotNone(response.data['results'][0]['proposition_id'])
        self.assertEqual(response.data['results'][0]['unread_cards_count'], 0)

    def test_moogt_response_contains_opposition_field(self):
        """
        If a moogt that has started is going to be in the response, it must contain the opposition field in the response.
        """
        opposition = create_user('opposition_user', 'test_password')
        create_moogt_with_user(self.user,
                               resolution="view content",
                               started_at_days_ago=1,
                               opposition=opposition)
        response = self.get(5, 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['results'][0]['opposition_id'])

    def test_poll_response_contains_essential_fields(self):
        """
        A poll response must contain necessary fields required by clients.
        """
        poll = create_poll(self.user, 'test title')
        response = self.get(5, 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['user_id'], poll.user.id)

    def test_success(self):
        """
        test successfully get all subscribed users content
        """
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1")
        poll = create_poll(self.user, "poll title")
        view = create_view(self.user, "view content", Visibility.PUBLIC.name)

        response = self.get(5, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pagination(self):
        """
        test tf the pagination is greater than zero then it should
        return content according to the page
        """
        view = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        poll = create_poll(self.user, "poll title 1")
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1")

        view_2 = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        moogt_2 = create_moogt_with_user(
            self.user, resolution="moogt resolution 3")
        poll_2 = create_poll(self.user, "poll title 2")

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['next'])

    def test_sorting(self):
        """
        Content should be returned with a sorting of time with
        the latest content created on top of the response
        """
        for i in range(5):
            create_view(self.user, f"view {i}", Visibility.PUBLIC.name)
            create_poll(self.user, f"poll {i}")
            create_moogt_with_user(
                self.user, resolution=f"resolution {i}", started_at_days_ago=1)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]['item_type'], 'moogt')
        self.assertEqual(response.data["results"]
                         [0]['resolution'], 'resolution 4')
        self.assertEqual(response.data["results"][1]['item_type'], 'poll')
        self.assertEqual(response.data["results"][1]['title'], 'poll 4')
        self.assertEqual(response.data["results"][2]['item_type'], 'view')
        self.assertEqual(response.data["results"][2]['content'], 'view 4')

    def test_no_moogt(self):
        """
        If no moogt exists in the current page but
        polls and views exist response should include them
        """
        view = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        poll = create_poll(self.user, "poll title 1")

        view_2 = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        poll_2 = create_poll(self.user, "poll title 2")

        response = self.get(2, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]['item_type'], 'poll')
        self.assertEqual(response.data["results"][0]['id'], poll_2.id)

    def test_no_view(self):
        """
        If no view exists in the current page
        but moogts and views exist response should include them
        """
        poll = create_poll(self.user, "poll title 1")
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1")

        view_2 = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        poll_2 = create_poll(self.user, "poll title 2")

        response = self.get(2, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]['item_type'], 'poll')
        self.assertEqual(response.data["results"][0]['id'], poll_2.id)

    def test_no_poll(self):
        """
        If no poll exist in the current page but
        moogts and vies exist response should include them
        """
        view = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1")

        view_2 = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        moogt_2 = create_moogt_with_user(
            self.user, resolution="moogt resolution 2", started_at_days_ago=1)
        moogt_3 = create_moogt_with_user(
            self.user, resolution="moogt resolution 3", started_at_days_ago=1)

        response = self.get(3, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]['item_type'], 'moogt')
        self.assertEqual(response.data["results"][0]['id'], moogt_3.id)

    def test_self_moogt_included(self):
        """
        test if self moogt are included in feed
        """
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1", started_at_days_ago=1)

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]['item_type'], 'moogt')
        self.assertEqual(response.data["results"][0]['id'], moogt.id)

    def test_self_moogt_included_in_moderator(self):
        """Test if self moogt are included in feed if the user is moderator"""

        moderator = create_user_and_login(self, 'moderator', 'password')
        user1 = create_user('username1', 'password')
        user2 = create_user('username2', 'password')

        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1", started_at_days_ago=1)

        moogt.set_moderator(moderator)
        moogt.save()

        response = self.get(5, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]['item_type'], 'moogt')
        self.assertEqual(response.data["results"][0]['id'], moogt.id)

    def test_self_poll_included(self):
        """
        test if self polls are included in feed
        """
        poll = create_poll(self.user, "poll title 1")

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["item_type"], "poll")
        self.assertEqual(response.data["results"][0]["id"], poll.id)

    def test_self_view_included(self):
        """
        test if self views are included in feed
        """
        view = create_view(self.user, "view title 1", Visibility.PUBLIC.name)

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["item_type"], "view")
        self.assertEqual(response.data["results"][0]["id"], view.id)

    def test_draft_view_excluded(self):
        """
        test if draft views are excluded from the feed
        """
        view = create_view(self.user, "view title 1", Visibility.PUBLIC.name)
        view.is_draft = True
        view.save()

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 0)

    def test_view_image_included_in_response(self):
        """
        If a view has images then it should be included in the Feed Response
        """
        view = create_view(self.user, "view title 1", Visibility.PUBLIC.name)

        view_image = ViewImage(view=view)
        view_image.save()

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["item_type"], "view")
        self.assertEqual(response.data["results"][0]["id"], view.id)
        self.assertEqual(len(response.data["results"][0]['images']), 1)

    def test_non_started_moogt_not_inlcuded(self):
        """
        If a moogt is not started then it should not be in the feed response
        """
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1")

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["overall_total"], 0)
        self.assertEqual(len(response.data['results']), 0)

    def test_reaction_view_without_statement(self):
        """
        If a reaction view is created by the creator of the parent view and it has no statement
        it should not be in the feed response. But the original view should be in the response
        """
        view = create_view(self.user, "view content", Visibility.PUBLIC.name)
        rxn_view = create_reaction_view(
            self.user, view, content=None, reaction_type=ReactionType.ENDORSE.name)

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 1)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], view.id)

    def test_reaction_without_statement_included_in_response(self):
        """
        If a reaction view is NOT created by the creator of the parent view and it has no statement
        it should be in the feed response.
        """
        view: View = create_view(
            self.user, "view title 1", Visibility.PUBLIC.name)
        user_1 = create_user("reactor", "password")
        self.follow(self.follower, user_1)
        rxn_view: View = create_reaction_view(
            user_1, view, content=None, reaction_type=ReactionType.ENDORSE.name)

        response = self.get(2, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 2)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['id'], rxn_view.pk)
        self.assertEqual(response.data['results'][1]['id'], view.pk)

    def test_reaction_without_statement_to_argument_included_in_response(self):
        """
        If a reaction view is NOT created by the moogt participant and it has no statement
        it should be in the feed response.
        """
        opposition = create_user("opposition", "password")
        proposition = create_user("proposition", "password")
        moogt = create_moogt_with_user(proposition, opposition=opposition, resolution="moogt resolution 1",
                                       started_at_days_ago=1)
        argument = create_argument(proposition, "test argument", moogt=moogt)

        user_1 = create_user("reactor", "password")
        self.follow(self.follower, user_1)

        rxn_view: View = create_reaction_view(user_1, argument, content=None, reaction_type=ReactionType.ENDORSE.name,
                                              type=ViewType.ARGUMENT_REACTION.name, )

        response = self.get(2, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 1)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], rxn_view.pk)
        self.assertEqual(response.data['results'][0]
                         ['parent']['stats']['endorse']['count'], 1)

    def test_reaction_argument_without_statement(self):
        """
        If a reaction argument is created by the creator of the parent argument and it has no statement
        it should not be in the feed response
        """
        argument = create_argument(self.user, "test argument")
        rxn_view = create_reaction_view(
            self.user, argument, content=None, reaction_type=ReactionType.ENDORSE.name)

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 0)
        self.assertEqual(len(response.data['results']), 0)

    def test_premiering_moogts_are_included(self):
        """
        Test if premiering moogts are included in the feed content of the moogt
        """
        moogt = create_moogt_with_user(
            self.user, resolution="moogt resolution 1")
        moogt.premiering_date = timezone.now() + timedelta(days=1)
        moogt.is_premiering = True
        moogt.save()

        response = self.get(1, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 1)
        self.assertEqual(response.data['results'][0]['id'], moogt.id)

    def test_reaction_without_statement_of_moogters_are_not_included(self):
        """
        If a moogter reacts without statement on an opponents card it should not be included in
        feed
        """
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(self.user, opposition=opposition, resolution="moogt resolution 1",
                                       started_at_days_ago=1)
        argument = create_argument(self.user, "test argument", moogt=moogt)

        rxn_view = create_reaction_view(
            opposition, argument, content=None, reaction_type=ReactionType.ENDORSE.name)

        response = self.get(5, 0)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_total'], 1)
        self.assertEqual(response.data['results'][0]['item_type'], 'moogt')


class ReplyCommentApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.commenter = create_user("username", "password")
        view = create_view(self.user, 'test view')
        self.comment = create_comment(view, self.commenter, 'test comment')

    def post(self, body=None):
        url = reverse('api:reply_comment', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_non_existing_comment(self):
        """
        If you try to reply to a comment that doesn't exist, it should respond
        with a not found response.
        """
        response = self.post({'reply_to': 404, 'comment': 'test comment'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reply_exceeds_max_thread_level(self):
        """
        If your reply level exceeds the COMMENTS_XTD_MAX_THREAD_LEVEL setting then you shouldn't be
        able to make comments.
        """
        self.comment.level = settings.COMMENTS_XTD_MAX_THREAD_LEVEL + 1
        self.comment.save()
        response = self.post(
            {'reply_to': self.comment.id, 'comment': 'test comment'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_a_reply(self):
        """
        If the request is valid, it should create a reply comment to the original comment.
        """
        response = self.post({'comment': 'test reply',
                              'reply_to': self.comment.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(XtdComment.objects.filter(
            parent_id=self.comment.id, comment='test reply').exists())
        self.assertEqual(self.commenter.notifications.count(), 1)
        self.assertEqual(self.commenter.notifications.first().type,
                         NOTIFICATION_TYPES.comment_reply)


class LikeViewCommentAPITests(APITestCase):
    def post(self, comment_id):
        url = reverse('api:like_comment', kwargs={
                      'version': 'v1', 'pk': comment_id})
        return self.client.post(url, {}, format='json')

    def test_like_a_comment(self):
        """
        Test liking a valid comment
        """
        user = create_user_and_login(self)

        view = create_view(user, "test view", Visibility.PUBLIC.name)
        comment = create_comment(view, user, "test comment")

        response = self.post(comment.id)
        comment.refresh_from_db()
        flag = comment.flags.first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(comment.flags.count(), 1)
        self.assertEqual(flag.flag, LIKEDIT_FLAG)
        self.assertEqual(user.notifications.count(), 0)

    def test_like_not_owned_comment(self):
        """
        If a comment is not owned by the liker the owner of the comment
        should get a notification
        """
        liker = create_user_and_login(self)
        user = create_user('username', 'password')

        view = create_view(user, "test view", Visibility.PUBLIC.name)
        comment = create_comment(view, user, "test comment")

        response = self.post(comment.id)
        comment.refresh_from_db()
        flag = comment.flags.first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(comment.flags.count(), 1)
        self.assertEqual(flag.flag, LIKEDIT_FLAG)
        self.assertEqual(user.notifications.count(), 1)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.comment_applaud)
        self.assertEqual(user.notifications.first(
        ).data['data']['original']['content_type'], 'view')

    def test_like_not_owned_reply(self):
        """
        If a comment reply is not owned by the liker the owner of the comment
        should get a notification
        """
        liker = create_user_and_login(self)
        user = create_user('username', 'password')

        view = create_view(user, "test view", Visibility.PUBLIC.name)
        comment = create_comment(view, user, "test comment")
        reply_comment = create_comment(comment, user, 'test reply comment')

        response = self.post(reply_comment.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.notifications.count(), 1)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.comment_applaud)
        self.assertEqual(user.notifications.first(
        ).data['data']['original']['content_type'], 'view')

    def test_like_unlike_a_comment(self):
        """
        Test liking and unliking a comment
        """
        creator = create_user('username', 'password')
        user = create_user_and_login(self)

        view = create_view(creator, "test view", Visibility.PUBLIC.name)
        comment = create_comment(view, creator, "test comment")

        response = self.post(comment.id)

        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type,
                         NOTIFICATION_TYPES.comment_applaud)

        response = self.post(comment.id)
        comment.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(comment.flags.count(), 0)
        self.assertEqual(creator.notifications.count(), 0)

    def test_like_non_existent_comment(self):
        """
        Test if comment doesn't exist it should not like it
        """
        user = create_user_and_login(self)

        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UnlikeViewCommentAPITests(APITestCase):
    def post(self, comment_id):
        url = reverse('api:unlike_comment', kwargs={
                      'version': 'v1', 'pk': comment_id})
        return self.client.post(url, {}, format='json')

    def test_unlike_a_comment(self):
        """
        Test unliking a valid liked comment
        """
        user = create_user_and_login(self)

        view = create_view(user, "test view", Visibility.PUBLIC.name)
        comment = create_comment(view, user, "test comment")

        flag, created = CommentFlag.objects.get_or_create(comment=comment,
                                                          user=user,
                                                          flag=LIKEDIT_FLAG)

        response = self.post(comment.id)
        comment.refresh_from_db()
        flag = comment.flags.first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(comment.flags.count(), 1)
        self.assertEqual(flag.flag, DISLIKEDIT_FLAG)

    def test_unlike_non_existent_comment(self):
        """
        Test unliking a non existent comment
        """
        user = create_user_and_login(self)

        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BrowseCommentReplyApiViewTests(APITestCase):
    def get(self, comment_id):
        url = reverse('api:browse_comment_replies', kwargs={
                      'version': 'v1', 'pk': comment_id})
        return self.client.get(url)

    def setUp(self):
        self.user = create_user_and_login(self)
        self.view = create_view(self.user, 'test content')
        self.comment = create_comment(self.view, self.user, 'test comment')

    def test_non_existing_comment(self):
        """
        For a non-existing comment it should respond with a not found response.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_browse_comment_replies(self):
        """
        It should return the replies for a particular comment.
        """
        reply_comment = create_comment(
            self.comment, self.user, 'test reply comment')
        response = self.get(self.comment.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], reply_comment.id)

    def test_browse_comment_with_replies_for_multiple_comments(self):
        """
        It should return the replies only to a particular comment not all the replies that exist.
        """
        comment_2 = create_comment(self.view, self.user, 'test comment 2')
        reply_comment = create_comment(
            self.comment, self.user, 'test reply comment')
        reply_comment_2 = create_comment(
            comment_2, self.user, 'test reply comment 2')

        response = self.get(self.comment.id)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], reply_comment.id)

        response = self.get(comment_2.id)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], reply_comment_2.id)


class RemoveCommentApiView(APITestCase):
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        view = create_view(self.user, 'test content')
        self.comment = create_comment(view, self.user, 'test comment')

    def post(self, comment_id):
        url = reverse('api:remove_comment', kwargs={
                      'version': 'v1', 'pk': comment_id})
        return self.client.post(url)

    def test_non_existing_comment(self):
        """
        If the comment doesn't exist, it should respond with a not found response.
        """
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_authenticated_user_trying_to_remove_comment(self):
        """
        It should respond with unauthorized response for non authenticated requests.
        """
        self.client.logout()
        response = self.post(self.comment.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_creator_trying_to_remove_comment(self):
        """
        Only the person who created the comment can remove the comment, otherwise it should
        respond with a forbidden response.
        """
        create_user_and_login(self, 'test_user1', 'test_comment')
        response = self.post(self.comment.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successfully_remove_a_comment(self):
        """
        If the request is valid, it should remove the comment.
        """
        response = self.post(self.comment.id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        xtd_comment = XtdComment.objects.get(pk=self.comment.id)
        self.assertFalse(xtd_comment.is_public)


class CommentDetailApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.view = create_view(self.user, 'test view')
        self.comment = create_comment(
            self.view, user=self.user, comment='test comment')

    def get(self, comment_id):
        url = reverse('api:comment_detail', kwargs={
                      'version': 'v1', 'pk': comment_id})
        return self.client.get(url)

    def test_non_logged_in_user(self):
        """Non logged in user should get a not authorized response."""
        self.client.logout()
        response = self.get(self.comment.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_comment(self):
        """Should respond with not found for non existent comment."""
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_comment(self):
        """Should get comment detail"""
        response = self.get(self.comment.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.comment.id)
        self.assertEqual(response.data['comment'], self.comment.comment)


class SearchResultsApiViewTests(APITestCase):
    def get(self, q, item_type=None, sort_by=None, category=None):
        url = reverse('api:search_results', kwargs={'version': 'v1'})
        if q:
            url += f'?q={q}&'
        if item_type:
            url += f'item_type={item_type}&'
        if sort_by:
            url += f'sort_by={sort_by}&'
        if category:
            url += f'category={category}'
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt1 = create_moogt(resolution='awesome', started_at_days_ago=1)
        self.moogt2 = create_moogt(started_at_days_ago=1)
        self.moogt2.description = 'better description'
        self.moogt2.save()
        self.moogt3 = create_moogt(resolution='magnificent')
        self.moogt3.premiering_date = timezone.now() + timedelta(days=1)
        self.moogt3.is_premiering = True
        self.moogt3.opposition = create_user("username", "password")
        self.moogt3.save()
        self.view = create_view(self.user, content='view1')
        self.user1 = create_user('yodi', 'pass123')
        self.argument = create_argument(
            self.user, "great argument", moogt=self.moogt1)
        self.poll = create_poll(self.user, 'test poll')

    def test_non_authenticated_user(self):
        """A non authenticated user cannot search items."""
        self.client.logout()
        response = self.get(None)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_without_providing_query(self):
        """If you don't provide the search term, then we can't do search."""
        response = self.get(None)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_moogts(self):
        """Search moogts which match the search term."""
        response = self.get('awesome')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.moogt1.id)

        response = self.get('better')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.moogt2.id)

    def test_search_moogts_that_are_premiering(self):
        """
        Search premiering moogts which match the search term
        """
        response = self.get('magnificent', category='premiering')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.moogt3.id)

    def test_search_moogts_by_moogters_names(self):
        """
        Search moogts by the name of the participant moogters
        """
        response = self.get('username', category='premiering')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.moogt3.id)

    def test_search_moogts_sort_by_popularity(self):
        """
        If one moogt has more followers than another moogt when searched then the moogt
        with more followers should come first in response when queried by popularity
        """
        moogt3 = create_moogt(
            resolution='better resolution', started_at_days_ago=1)
        moogt3.followers.add(self.user1)

        response = self.get('better', item_type="moogt", sort_by="popularity")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], moogt3.id)
        self.assertEqual(response.data['results'][1]['id'], self.moogt2.id)

    def test_search_views(self):
        """Search views which match the search term."""
        response = self.get('view1', 'view')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.view.id)
        self.assertEqual(response.data['results']
                         [0]['content'], self.view.content)

    def test_search_views_sort_by_popularity(self):
        """
        If one view has more reactions than another view when searched then the view
        with more reactions should come first in the response when queried by popularity
        """
        rxn_view = create_view(self.user, content='view2')
        rxn_view.parent_view = self.view
        rxn_view.type = ViewType.VIEW_REACTION.name
        rxn_view.save()
        response = self.get('view', 'view', sort_by='popularity')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.view.id)

        response = self.get(
            'view', 'view', sort_by='popularity', category='reaction_view')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], rxn_view.id)

    def test_search_users(self):
        """Search users which match the search term."""
        response = self.get('yodi', 'user')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.user1.id)
        self.assertEqual(response.data['results']
                         [0]['username'], self.user1.username)

    def test_search_polls(self):
        """Search polls which match the search term."""
        response = self.get('test poll', 'poll')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.poll.id)
        self.assertEqual(response.data['results'][0]['title'], self.poll.title)

    def test_search_users_sort_by_popularity(self):
        """
        When searched list of users should come sorted by the number of followers
        the users have
        """
        user2 = create_user('yodi1', 'pass123')

        user2.followers.add(self.user1)
        self.user1.followings.add(self.user1)

        response = self.get('yodi', 'user', 'popularity')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], user2.id)
        self.assertEqual(response.data['results'][1]['id'], self.user1.id)

    def test_search_users_subscribed_category(self):
        """Should get users you've subscribed to only."""
        user2 = create_user('yodi1', 'pass123')

        response = self.get('yodi1', 'user', category='subscribed')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

        user2.followers.add(self.user)
        self.user.followings.add(user2)

        response = self.get('yodi1', 'user', category='subscribed')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user2.id)

    def test_search_users_unsubscribed_category(self):
        """Should get users you're not subscribed to."""
        user2 = create_user('yodi1', 'pass123')

        response = self.get('yodi1', 'user', category='unsubscribed')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_search_arguments(self):
        """
        Search arguments which match the search term.
        """
        response = self.get('argument', item_type='argument')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.argument.id)

    def test_search_arguments_sort_by_popularity(self):
        """
        If one argument has more reactions than another argument when searched then the argument
        with more reactions should come first in the response when queried by popularity
        """
        argument1 = create_argument(
            self.user, "great argument 2", moogt=self.moogt1)
        rxn_view = create_reaction_view(self.user, argument1)

        response = self.get(
            'argument', item_type='argument', sort_by='popularity')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], argument1.id)
        self.assertEqual(response.data['results'][1]['id'], self.argument.id)

    def test_draft_post_should_be_excluded(self):
        """
        If a post is a draft post then it should not be included in the search result
        """
        self.view.is_draft = True
        self.view.save()

        response = self.get('view', item_type='view', sort_by='popularity')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


class SearchResultsCountApiViewTests(APITestCase):
    def get(self, q=None):
        url = reverse('api:search_results_count', kwargs={'version': 'v1'})
        if q:
            url += f'?q={q}'
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_without_providing_a_search_query_param(self):
        """The search query param should be required."""
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_user(self):
        """An anonymous user should get a not authorized response."""
        self.client.logout()
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_moogts_count(self):
        """Should get moogts_count properly."""
        moogt = create_moogt('test moogt', started_at_days_ago=1)
        response = self.get(q='test')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogts_count'], 1)

        response = self.get(q='xyz')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['moogts_count'], 0)

    def test_get_views_count(self):
        """Should get views_count properly."""
        create_view(user=self.user, content='test view')
        response = self.get(q='test')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['views_count'], 1)

        response = self.get(q='x')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['views_count'], 0)

    def test_get_polls_count(self):
        """Should get polls_count properly."""
        create_poll(user=self.user, title='test poll')
        response = self.get(q='test')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['polls_count'], 1)

        response = self.get(q='option 1')
        self.assertEqual(response.data['polls_count'], 1)

        response = self.get(q='x')
        self.assertEqual(response.data['polls_count'], 0)

    def test_get_arguments_count(self):
        """Should get arguments_count properly."""
        create_argument(self.user, argument='test argument')

        response = self.get(q='test')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['arguments_count'], 1)

        response = self.get(q='x')
        self.assertEqual(response.data['arguments_count'], 0)

    def test_get_accounts(self):
        """Should get accounts_count properly."""
        response = self.get(q=self.user.username)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['accounts_count'], 0)

        create_user(username='mgtruser1', password='testpass')
        response = self.get(q='mgtr')
        self.assertEqual(response.data['accounts_count'], 1)


class TelegramOptInApiViewTests(APITestCase):
    def post(self, chat_id=None):
        url = reverse('api:telegram_opt_in', kwargs={'version': 'v1'}) + '?'

        if chat_id:
            url += 'cid=' + str(chat_id)

        return self.client.post(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    @patch("moogter_bot.bot.bot.sendMessage")
    def test_success(self, mock_function):
        response = self.post(chat_id=1)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(TelegramChatToUser.objects.count(), 1)
        mock_function.assert_called_once()

    @patch("moogter_bot.bot.bot.sendMessage")
    def test_no_chat_id(self, mock_function):
        """
        If no chat id is provided request should fail
        """
        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TelegramChatToUser.objects.count(), 0)
        mock_function.sendMessage.assert_not_called()
