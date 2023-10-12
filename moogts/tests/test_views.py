# Create your tests here.
import datetime
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from api.enums import Visibility, ViewType, ReactionType
from api.mixins import ViewArgumentReactionMixin
from api.models import Tag
from api.tests.tests import create_user_and_login
from api.tests.utility import create_moogt_with_user, create_user, create_user_and_login, create_mini_suggestion, \
    create_invitation, generate_photo_file, create_argument, create_reaction_view, create_moogt_stats
from arguments.models import Argument
from chat.models import MessageSummary
from invitations.models import Invitation
from meda.enums import MoogtType, MoogtEndStatus, ActivityStatus, ArgumentType
from meda.models import AbstractActivityAction
from meda.tests.test_models import create_moogt
from invitations.models import ModeratorInvitation
from moogtmeda.settings import MEDIA_ROOT
from moogts.enums import MiniSuggestionState, MoogtActivityType, DonationLevel
from moogts.models import Moogt, MoogtMiniSuggestion, MoogtBanner, MoogtActivity, Donation, MoogtReport, ReadBy, \
    MoogtStatus, MoogtActivityBundle
from moogts.tests.factories import MoogtFactory
from notifications.models import NOTIFICATION_TYPES
from users.models import MoogtMedaUser, CreditPoint, Activity, Wallet
from users.tests.factories import BlockingFactory
from views.models import View


class MoogtListViewTests(APITestCase):
    def get(self, premiering_only='false', trending='false'):
        url = reverse('api:moogts:list',
                      kwargs={'version': 'v1'}) + '?premiering_only=' + premiering_only + '&trending=' + trending

        return self.client.get(url)

    def test_no_moogt(self):
        """
        When no moogts exist, it must not have any result.
        """
        response = self.get()

        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.status_code, 200)

    def test_a_moogt_exist(self):
        """
        If a moogt exists, it should be included in the response.
        """
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        response = self.get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['resolution'], moogt.get_resolution())
        self.assertEqual(
            response.data['results'][0]['proposition_id'], moogt.get_proposition().id)

    def test_premiering_moogts_are_included(self):
        """
        Test if premiering moogts are included in the feed content of the moogt
        when specifically asked
        """
        moogt = create_moogt(resolution='test resolution')
        moogt.premiering_date = timezone.now() + timedelta(days=1)
        moogt.is_premiering = True
        moogt.save()

        response = self.get(premiering_only='true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], moogt.id)

    def test_two_moogts_exists(self):
        """
        If two moogts are created, the most recent should be first.
        """
        moogt_1 = create_moogt(resolution='resolution1', started_at_days_ago=1)
        moogt_2 = create_moogt(resolution='resolution2', started_at_days_ago=1)
        response = self.get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]
                         ['resolution'], moogt_2.get_resolution())
        self.assertEqual(
            response.data['results'][0]['proposition_id'], moogt_2.get_proposition().id)
        self.assertEqual(response.data['results'][1]
                         ['resolution'], moogt_1.get_resolution())
        self.assertEqual(
            response.data['results'][1]['proposition_id'], moogt_1.get_proposition().id)

    def test_feed_only(self):
        """
        If feed_only query param is set to true, then it should only include the feed in the response
        """
        moogt = create_moogt('resolution', started_at_days_ago=1)
        create_moogt('resolution2', started_at_days_ago=1)

        user = create_user_and_login(self)
        moogt.get_proposition().followers.add(user)
        moogt.get_proposition().save()

        user.followings.add(moogt.get_proposition())
        user.save()

        url = reverse('api:moogts:list', kwargs={
                      'version': 'v1'}) + '?feed_only=true'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['resolution'], moogt.get_resolution())

    def test_exclude_non_started_moogt(self):
        """
        Non-started moogts should not be included in the response
        """
        moogt = create_moogt('resolution')
        moogt_1 = create_moogt('resolution2', started_at_days_ago=1)

        user = create_user_and_login(self)

        response = self.get()

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], moogt_1.id)

    def test_moogt_stats_with_proposition_endorsement(self):
        """
        Test creating an endorsement by a non moogter on a proposition's argument for a moogt
        should return the with the proposition_endorsement incremented
        """
        proposition = create_user_and_login(self)
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, started_at_days_ago=1, opposition=opposition)
        argument_prop = create_argument(proposition, "argument 1", moogt=moogt)
        argument_prop_2 = create_argument(
            proposition, "argument 2", moogt=moogt)
        argument_opp = create_argument(opposition, "argument 3", moogt=moogt)

        user = create_user("username", "password")
        user_2 = create_user("username_1", "password")

        rxn_view_1 = create_reaction_view(
            user, argument_prop, type=ViewType.ARGUMENT_REACTION.name)
        create_reaction_view(user, argument_prop,
                             type=ViewType.ARGUMENT_REACTION.name)
        create_reaction_view(user_2, argument_prop,
                             type=ViewType.ARGUMENT_REACTION.name)
        create_reaction_view(user, argument_prop_2,
                             type=ViewType.ARGUMENT_REACTION.name)
        rxn_view_2 = create_reaction_view(
            user_2, argument_prop_2, type=ViewType.ARGUMENT_REACTION.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_endorsement_count'], 4)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_disagreement_count'], 0)
        self.assertEqual(response.data['results'][0]
                         ['stats']['opposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['opposition_disagreement_count'], 0)

        rxn_view_2.delete()
        ViewArgumentReactionMixin.update_argument(argument_prop_2)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_endorsement_count'], 3)

    def test_moogt_stats_with_proposition_disagreement(self):
        """
        Test creating an disagreements by a non moogter on a proposition's argument for a moogt
        should return the with the proposition_disagreement incremented
        """
        proposition = create_user_and_login(self)
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, started_at_days_ago=1, opposition=opposition)
        argument_prop = create_argument(proposition, "argument 1", moogt=moogt)
        argument_opp = create_argument(opposition, "argument 2", moogt=moogt)

        user = create_user("username", "password")
        rxn_view = create_reaction_view(user, argument_prop, type=ViewType.ARGUMENT_REACTION.name,
                                        reaction_type=ReactionType.DISAGREE.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_disagreement_count'], 1)
        self.assertEqual(response.data['results'][0]
                         ['stats']['opposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['opposition_disagreement_count'], 0)

    def test_moogt_stats_with_opposition_endorsement(self):
        """
        Test creating an agreement by a non moogter on a opposition's argument for a moogt
        should return the with the opposition_endorsement incremented
        """
        proposition = create_user_and_login(self)
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, started_at_days_ago=1, opposition=opposition)
        argument_prop = create_argument(proposition, "argument 1", moogt=moogt)
        argument_opp = create_argument(opposition, "argument 2", moogt=moogt)

        user = create_user("username", "password")
        rxn_view = create_reaction_view(user, argument_opp, type=ViewType.ARGUMENT_REACTION.name,
                                        reaction_type=ReactionType.ENDORSE.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_disagreement_count'], 0)
        self.assertEqual(response.data['results'][0]
                         ['stats']['opposition_endorsement_count'], 1)
        self.assertEqual(
            response.data['results'][0]['stats']['opposition_disagreement_count'], 0)

    def test_moogt_stats_with_opposition_disagremment(self):
        """
        Test creating an disagreements by a non moogter on a opposition's argument for a moogt
        should return the with the opposition_disagreement incremented
        """
        proposition = create_user_and_login(self)
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, started_at_days_ago=1, opposition=opposition)
        argument_prop = create_argument(proposition, "argument 1", moogt=moogt)
        argument_opp = create_argument(opposition, "argument 2", moogt=moogt)

        user = create_user("username", "password")
        rxn_view = create_reaction_view(user, argument_opp, type=ViewType.ARGUMENT_REACTION.name,
                                        reaction_type=ReactionType.DISAGREE.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_disagreement_count'], 0)
        self.assertEqual(response.data['results'][0]
                         ['stats']['opposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['opposition_disagreement_count'], 1)

    def test_duplicate_users_reacting_on_moogt_arguments(self):
        """
        Test creating an endorsement twice by a non moogter on a proposition's argument for a moogt
        should return the with the proposition_endorsement incremented only by one
        """
        proposition = create_user_and_login(self)
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, started_at_days_ago=1, opposition=opposition)
        argument_prop = create_argument(proposition, "argument 1", moogt=moogt)
        argument_opp = create_argument(opposition, "argument 2", moogt=moogt)

        user = create_user("username", "password")
        rxn_view = create_reaction_view(
            user, argument_prop, type=ViewType.ARGUMENT_REACTION.name)
        rxn_view = create_reaction_view(
            user, argument_prop, type=ViewType.ARGUMENT_REACTION.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_endorsement_count'], 1)
        self.assertEqual(
            response.data['results'][0]['stats']['proposition_disagreement_count'], 0)
        self.assertEqual(response.data['results'][0]
                         ['stats']['opposition_endorsement_count'], 0)
        self.assertEqual(
            response.data['results'][0]['stats']['opposition_disagreement_count'], 0)

    # This test is failing just because our tests are using SQLite db.
    # Trying to get duration as seconds(or integers) is different depending on the database.
    # Since we're using PostgreSQL this test is commented out.
    # def test_trending_moogts_sorted_appropriately(self):
    #     """
    #     If a moogt has more followers than another moogt while being querying for trending it should
    #     sort based on follower count descendingly
    #     """
    #     proposition = create_user_and_login(self)
    #     user = create_user("user", "password")
    #     moogt_1 = create_moogt_with_user(proposition, started_at_days_ago=1, opposition=True)
    #     moogt_2 = create_moogt_with_user(proposition, started_at_days_ago=1, opposition=True)
    #     moogt_3 = create_moogt_with_user(proposition, started_at_days_ago=1, opposition=True)
    #
    #     moogt_2.followers.add(user)
    #     moogt_2.score.maybe_update_score()
    #
    #     response = self.get(trending='true')
    #
    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(response.data['results'][0]['id'], moogt_2.pk)


class MoogtCreateViewTests(APITestCase):
    def post(self, data=None):
        url = reverse('api:moogts:create', kwargs={'version': 'v1'})
        return self.client.post(url, data, format='json')

    def test_with_no_authenticated_user(self):
        """
        If there is no authenticated user, it should respond with not authorized status code
        """
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_with_missing_resolution(self):
        """
        If the resolution is missing, it should respond with bad request status code
        """
        create_user_and_login(self)
        response = self.post({'argument': 'test argument'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # def test_with_missing_argument(self):
    #     """
    #     If missing argument, it should respond with bad request status code
    #     """
    #     create_user_and_login(self)
    #     response = self.post({'resolution': 'test resolution'})
    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    #     self.assertTrue(Moogt.objects.filter(id=response.data['id']).exists())

    # def test_with_invalid_invitee(self):
    #     """
    #     If the invitee does not exist, it should return 404
    #     """
    #     create_user_and_login(self)
    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument',
    #                           'invitee_id': 404})
    #     self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # def test_where_invitee_and_inviter_are_the_same(self):
    #     """
    #     If the invitee is the same as the invitee, it should respond with bad request
    #     """
    #     user = create_user_and_login(self)
    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument',
    #                           'invitee_id': user.id})
    #     self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # def test_with_a_valid_invitee(self):
    #     """
    #     If the invitee is valid, it should create an invitation
    #     """
    #     inviter = create_user_and_login(self)
    #     invitee = create_user('invitee_user', 'testpassword')
    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument',
    #                           'invitee_id': invitee.id})

    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     invitation = Invitation.objects.get(moogt__id=response.data['id'])
    #     self.assertEqual(invitation.inviter, inviter)
    #     self.assertEqual(invitation.invitee, invitee)

    #     # Make sure a notification is sent
    #     invitee = MoogtMedaUser.objects.get(id=invitee.id)
    #     self.assertEqual(invitee.notifications.count(), 1)

    def test_with_invalid_visibility(self):
        """
        If the visibility is different from the available options, it shouldn't create a moogt
        """
        create_user_and_login(self)
        response = self.post({'resolution': 'test resolution',
                              'argument': 'test argument',
                              'visibility': 'invalid'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # def test_default_visibility_is_to_the_public(self):
    #     """
    #     If visibility is not provided in the request, the moogt should be visibile to the public
    #     by default
    #     """
    #     create_user_and_login(self)
    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument'})
    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     self.assertEqual(response.data['visibility'], Visibility.PUBLIC.name)

    # def test_default_type_should_be_duo_moogt(self):
    #     """
    #     If the type of the moogt that is going to be created is not provided in the request,
    #     by default it should be a duo moogt
    #     """
    #     create_user_and_login(self)
    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument'})
    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     self.assertEqual(response.data['type'], MoogtType.DUO.name)

    def test_invalid_moogt_type(self):
        """
        If the request contains an invalid moogt type, it should not create a new moogt
        """
        create_user_and_login(self)
        response = self.post({'resolution': 'test resolution',
                              'argument': 'test argument',
                              'type': 'invalid'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # def test_tags_provided_by_user(self):
    #     """
    #     If tags are provided by the user, it should create the moogt with those tags
    #     """
    #     create_user_and_login(self)
    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument',
    #                           'tags': [{'name': 'tag1'}, {'name': 'tag2'}]})

    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    #     moogt = Moogt.objects.get(pk=response.data['id'])
    #     self.assertEqual(moogt.tags.count(), 2)

    # def test_moderator_given_in_the_request(self):
    #     """
    #     If the moderator is provided it should create the invitation properly.
    #     """
    #     create_user_and_login(self)
    #     invitee = create_user('invitee_user', 'testpassword')
    #     moderator = create_user('moderator_user', 'testpassword')

    #     response = self.post({'resolution': 'test resolution',
    #                           'argument': 'test argument',
    #                           'invitee_id': invitee.id,
    #                           'moderator_id': moderator.id})

    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     moogt = Moogt.objects.get(pk=response.data['id'])
    #     self.assertEqual(moogt.moderator, None)

    #     invitation = ModeratorInvitation.objects.get(moderator=moderator)
    #     self.assertIsNotNone(invitation)

    # def test_create_moogt_with_banner(self):
    #     """If a banner image is given the moogt should be created with the banner."""
    #     create_user_and_login(self)
    #     banner = MoogtBanner.objects.create()
    #     response = self.post({'resolution': 'test resolution',
    #                           'banner_id': banner.id})
    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     self.assertEqual(response.data['banner_id'], banner.id)


class MoogtDetailViewTests(APITestCase):
    def get(self, moogt_id):
        url = reverse('api:moogts:detail', kwargs={
                      'pk': moogt_id, 'version': 'v1'})
        return self.client.get(url)

    def test_moogt_does_not_exist(self):
        """
        If the moogt with the given id doesn't exist, it must respond with 404 response code
        """
        response = self.get(404)
        self.assertEqual(response.status_code, 404)

    def test_moogt_exists(self):
        """
        If the moogt with the given id exists, it should respond correctly with status code 200
        """
        moogt = create_moogt('test resolution')
        create_moogt_stats(moogt)
        response = self.get(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['resolution'], moogt.get_resolution())

    def test_last_opened_moogt(self):
        """
        If an authenticated user views a given moogt the last_opened_moogt field gets retrieved
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution='resolution1')
        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_moogt, moogt)

    def test_last_opened_non_participating_moogt(self):
        """
        If an authenticated user views a given moogt but is not an opposition nor a proposition
        it should not update the last_opened_moogt field
        """
        moogt = create_moogt(resolution="resolution")
        user = create_user_and_login(self)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_moogt, moogt)

    def test_last_opened_moogt_updated(self):
        """
        If an authenticated user views two moogts the last_opened_moogt should be the last one the user viewed
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution='resoltion1')
        moogt2 = create_moogt_with_user(user, resolution='resoltion2')

        response = self.get(moogt.id)
        response = self.get(moogt2.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_moogt, moogt2)

    def test_last_opened_following_moogt(self):
        """
        If an authenticated user views a given moogt the last_opened_moogt field gets retrieved
        """
        moogt = create_moogt(resolution='resolution1')
        user = create_user_and_login(self)
        moogt.followers.add(user)
        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_following_moogt, moogt)

    def test_last_opened_following_moogt_updated(self):
        """
        If an authenticated user views two moogts the last_opened_following_moogt should be the last one the user viewed
        """
        moogt = create_moogt(resolution='resoltion1')
        moogt2 = create_moogt(resolution='resoltion2')
        user = create_user_and_login(self)

        moogt.followers.add(user)
        moogt2.followers.add(user)

        response = self.get(moogt.id)
        response = self.get(moogt2.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_following_moogt, moogt2)

    def test_last_opened_followed_unfollowed_moogt(self):
        """
        If an authenticated user views two moogts with one followed moogt and another unfollowed
        the two should be updated accordingly
        """
        user = create_user_and_login(self)

        moogt = create_moogt(resolution='resoltion1')
        moogt2 = create_moogt_with_user(user, resolution='resoltion2')

        moogt.followers.add(user)

        response = self.get(moogt.id)
        response = self.get(moogt2.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_following_moogt, moogt)
        self.assertEqual(MoogtMedaUser.objects.get(
            pk=user.id).last_opened_moogt, moogt2)

    def test_update_stats(self):
        """
        If the moogt with the given id exists, the moogt stat should be updated
        """
        create_user_and_login(self)

        moogt = create_moogt(resolution='resolution1')
        create_moogt_stats(moogt)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moogt = Moogt.objects.get(pk=moogt.id)
        self.assertEqual(moogt.stats.view_count, 1)

    def test_someone_viewing_proposition_moogt(self):
        """
        If someone else views a moogt, the proposition must be awarded points
        """
        proposition_user = create_user('proposition_user', '12345')

        self.assertEqual(proposition_user.profile.xp(), 0)

        moogt = create_moogt(started_at_days_ago=1)
        create_moogt_stats(moogt)
        moogt.set_proposition(proposition_user)
        moogt.save()

        user = create_user_and_login(self)

        self.get(moogt.id)

        proposition_user = MoogtMedaUser.objects.get(pk=proposition_user.id)
        user = MoogtMedaUser.objects.get(pk=user.id)

        # Patching the val() method inside the CreditPoint model so that this test won't break
        # if the implementation is ever changed.
        CreditPoint.val = lambda s: 10

        self.assertEqual(proposition_user.profile.xp(), 10)
        self.assertEqual(user.profile.xp(), 0)

    def test_someone_viewing_opposition_moogt(self):
        """
        If someone else views a moogt, the opposition must be awarded points
        """
        opposition_user = create_user('opposition_user', '12345')

        self.assertEqual(opposition_user.profile.xp(), 0)

        moogt = create_moogt(started_at_days_ago=1)
        create_moogt_stats(moogt)
        moogt.set_opposition(opposition_user)
        moogt.save()

        user = create_user_and_login(self)
        self.get(moogt.id)
        opposition_user = MoogtMedaUser.objects.get(pk=opposition_user.id)
        user = MoogtMedaUser.objects.get(pk=user.id)

        CreditPoint.val = lambda s: 10

        self.assertEqual(opposition_user.profile.xp(), 10)
        self.assertEqual(user.profile.xp(), 0)

    def test_user_is_current_turn(self):
        """
        If it's a users turn in a moogt there is_current_turn field in the response should be true
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=proposition, started_at_days_ago=1, opposition=opposition,
                                       has_opening_argument=True)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['is_current_turn'], False)

    def test_next_turn_user_id(self):
        """
        Response should include the next turns user id
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['next_turn_user_id'], proposition.id)

    def test_pending_activities_included_in_response(self):
        """If there are pending activities for the moogt, it should be included in the response."""
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)
        moogt_activity = MoogtActivity.objects.create(
            moogt=moogt, type=MoogtActivityType.CARD_REQUEST.value)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['activities'])
        self.assertEqual(response.data['activities']
                         [0]['id'], moogt_activity.id)

    def test_non_pending_activities_should_not_be_included_in_the_response(self):
        """If there are non pending activities, they should not be included in the response."""
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)
        moogt_activity = MoogtActivity.objects.create(moogt=moogt,
                                                      type=MoogtActivityType.CARD_REQUEST.value,
                                                      status=ActivityStatus.DECLINED.value)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['activities'])
        self.assertEqual(len(response.data['activities']), 0)

    def test_total_and_your_donations_included_in_response(self):
        """
        If request is coming from a moogter total donations and your donations should be
        included in the response
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)

        donation = Donation.objects.create(moogt=moogt, amount=1, level=DonationLevel.LEVEL_1.name,
                                           donation_for_proposition=True, user=opposition)
        donation2 = Donation.objects.create(moogt=moogt, amount=5, level=DonationLevel.LEVEL_2.name,
                                            donation_for_proposition=False, user=opposition)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_donations'], 6)
        self.assertEqual(response.data['your_donations'], 1)

    def test_total_and_your_donations_excluded_for_non_moogters(self):
        """
        If request is coming from a non-moogter total donations and your donations should be
        excluded from the response
        """
        opposition = create_user("opposition", "password")
        proposition = create_user("proposition", "password")
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)

        user = create_user_and_login(self)

        donation = Donation.objects.create(moogt=moogt, level=DonationLevel.LEVEL_1.name, donated_for=proposition,
                                           donation_for_proposition=True, user=user)
        donation2 = Donation.objects.create(moogt=moogt, level=DonationLevel.LEVEL_2.name, donated_for=opposition,
                                            donation_for_proposition=False, user=user)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse('total_donations' in response.data.keys())
        self.assertFalse('your_donations' in response.data.keys())

    def test_arguments_count(self):
        """
        If a moogt has an argument response should include the number of arguments that the moogt consists
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user=proposition, started_at_days_ago=1, opposition=opposition)
        argument = create_argument(
            moogt=moogt, argument='test argument', user=proposition)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['arguments_count'], 1)

    def test_expire_activities_for_ended_moogts(self):
        """
        If a moogt has ended then all the pending Requests should be set to expired
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt: Moogt = create_moogt_with_user(proposition_user=proposition, started_at_days_ago=1,
                                              opposition=opposition, has_ended=True)
        activity: MoogtActivity = MoogtActivity.objects.create(moogt=moogt,
                                                               type=MoogtActivityType.CARD_REQUEST.value,
                                                               user=proposition)

        response = self.get(moogt.pk)

        activity.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(activity.status, ActivityStatus.EXPIRED.value)
        self.assertEqual(activity.type, MoogtActivityType.CARD_REQUEST.name)

    def test_only_pending_activities_should_be_attached_with_moogt(self):
        """only activities which are pending should come attached with a moogt"""
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt: Moogt = create_moogt_with_user(proposition_user=proposition, started_at_days_ago=1,
                                              opposition=opposition)

        moogt_activity = MoogtActivity.objects.create(moogt=moogt,
                                                      type=MoogtActivityType.CARD_REQUEST.value,
                                                      status=ActivityStatus.ACCEPTED.value)

        moogt_activity_2 = MoogtActivity.objects.create(moogt=moogt,
                                                        type=MoogtActivityType.PAUSE_REQUEST.value,
                                                        status=ActivityStatus.DECLINED.value)

        moogt_activity_3 = MoogtActivity.objects.create(moogt=moogt,
                                                        type=MoogtActivityType.END_REQUEST.value,
                                                        status=ActivityStatus.EXPIRED.value)

        response = self.get(moogt.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['activities']), 0)

    def test_viewing_a_deleted_moogt(self):
        """
        If a user tried to access a deleted moogt it will indicate it
        was deleted and do not show any content
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)
        moogt: Moogt = create_moogt_with_user(proposition_user=proposition, started_at_days_ago=1,
                                              opposition=opposition)
        moogt.delete()

        response = self.get(moogt.pk)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_premiering_moogt_that_ended_premiering(self):
        """
        If a moogt has ended it's premiering period it's is_premiering field should be set
        to False
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(
            proposition, resolution="moogt resolution 1", opposition=opposition)
        moogt.premiering_date = timezone.now() - timedelta(days=1)
        moogt.is_premiering = True
        moogt.save()

        response = self.get(moogt.pk)

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['is_premiering_moogt'], False)
        self.assertEqual(moogt.started_at, moogt.premiering_date)

    def test_viewing_moogt_detail_creates_moogt_started_status(self):
        """
        If a moogt has started and it has started it should show the moogt has started status object
        """
        opposition = create_user("opposition", "password")
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(proposition, resolution="moogt resolution 1", opposition=opposition,
                                              started_at_days_ago=1)

        response = self.get(moogt.pk)

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.statuses.count(), 1)
        self.assertEqual(moogt.statuses.first().status,
                         MoogtStatus.STATUS.started)

    def test_viewing_moogt_detail_creates_duration_over_status(self):
        """
        If a moogt has expired it should create the moogt duration over status
        """
        opposition = create_user("opposition", 'password')
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(proposition, resolution="moogt resolution 1", opposition=opposition,
                                              started_at_days_ago=3)
        argument_opp = create_argument(opposition, moogt)

        response = self.get(moogt.pk)

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.statuses.count(), 2)
        self.assertEqual(moogt.statuses.first().status,
                         MoogtStatus.STATUS.started)
        self.assertEqual(moogt.statuses.last().status,
                         MoogtStatus.STATUS.duration_over)

    def test_viewing_moogt_detail_does_not_end_moogt(self):
        """
        If a moogt has started and it's duration has expired and the last person to create argument
        after the moogt expired is the proposition then the moogt should not end
        """
        opposition = create_user("opposition", 'password')
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(proposition, resolution="moogt resolution 1", opposition=opposition,
                                              started_at_days_ago=3)

        # creates the moogt duration over status
        self.get(moogt.pk)

        argument_prop = create_argument(proposition, moogt)

        response = self.get(moogt.pk)

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.statuses.count(), 2)
        self.assertEqual(moogt.statuses.first().status,
                         MoogtStatus.STATUS.started)
        self.assertEqual(moogt.statuses.last().status,
                         MoogtStatus.STATUS.duration_over)
        self.assertEqual(moogt.get_has_ended(), False)

    def test_viewing_moogt_detail_ends_moogt(self):
        """
        If a moogt has started and it's duration has expired and the last person to create argument
        after the moogt expired is the opposition then the moogt should end
        """
        opposition = create_user("opposition", 'password')
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(proposition, resolution="moogt resolution 1", opposition=opposition,
                                              started_at_days_ago=3)

        # creates the moogt duration over status
        self.get(moogt.pk)

        argument_opp = create_argument(opposition, 'argument', moogt=moogt)

        response = self.get(moogt.pk)

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.statuses.count(), 2)
        self.assertEqual(moogt.statuses.first().status,
                         MoogtStatus.STATUS.started)
        self.assertEqual(moogt.statuses.last().status,
                         MoogtStatus.STATUS.duration_over)
        self.assertEqual(moogt.get_has_ended(), True)


class AcceptMoogtViewTests(APITestCase):
    def post(self, moogt_id):
        url = reverse('api:moogts:accept', kwargs={
                      'pk': moogt_id, 'version': 'v1'})
        return self.client.post(url)

    def test_user_is_not_authenticated(self):
        """
        If user is not authenticated, it should not set user as opposition
        """
        moogt = create_moogt()
        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_where_opposition_has_been_set_already(self):
        """
        If opposition has been set for the moogt, it should not set user as opposition
        """
        create_user_and_login(self)
        moogt = create_moogt(opposition=True)
        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_where_user_is_the_proposition(self):
        """
        If the user is the proposition, it should not set user as opposition
        """
        user = create_user_and_login(self)
        moogt = create_moogt()
        moogt.set_proposition(user)
        moogt.save()

        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_non_existing_moogt(self):
        """
        If the moogt does not exist, it should return a not found response
        """
        create_user_and_login(self)
        response = self.post(404)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_valid_request(self):
        """
        If the request is valid, it should set the user as opposition.
        """
        user = create_user_and_login(self)
        moogt = create_moogt()

        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moogt = Moogt.objects.get(pk=moogt.id)
        self.assertEqual(moogt.get_opposition(), user)
        self.assertEqual(moogt.func_has_started(), True)
        self.assertEqual(moogt.get_started_at().replace(second=0, microsecond=0),
                         timezone.now().replace(second=0, microsecond=0))


class FollowMoogtAPIViewTests(APITestCase):
    def post(self, pk):
        url = reverse('api:moogts:follow_moogt', kwargs={
                      'version': 'v1', 'pk': pk})
        return self.client.post(url)

    def test_unauthenticated_user(self):
        """
        If a user is not authenticated, it should not allow them to follow a moogt
        """
        moogt = create_moogt_with_user(
            create_user('test_user', 'test_password'))
        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_none_existing_moogt(self):
        """
        If the moogt does not exist, it should respond with not found response
        """
        create_user_and_login(self)
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_follower_already_in_moogt_followers_list(self):
        """
        If a person who is following the moogt tries to follow that moogt,
        it should remove that person from the moogt's followers list
        """
        user = create_user_and_login(self)
        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)
        moogt.followers.add(user)

        self.assertEqual(moogt.followers.count(), 1)
        self.post(moogt.id)
        self.assertEqual(moogt.followers.count(), 0)

    def test_proposition_user_trying_to_follow_moogt(self):
        """
        A proposition user cannot follow his own moogt
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_opposition_user_trying_to_follow_moogt(self):
        """
        An opposition user cannot follow a moogt he's participating in
        """
        user = create_user_and_login(self)
        moogt = Moogt(proposition=create_user('proposition_user', 'test_password'),
                      opposition=user)
        moogt.save()

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_activity_must_be_recorded_for_a_valid_request(self):
        """
        If the request is valid, the activity must be recorded
        """
        create_user_and_login(self)
        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Activity.objects.count(), 1)

    def test_followers_count_should_be_included_in_the_response(self):
        """
        If a user successfully follows a moogt, the followers count should be set to 1 in the response
        """
        create_user_and_login(self)
        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['followers_count'], 1)

        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['followers_count'], 0)

    def test_follow_unfollow_should_have_notifications_updated_accordingly(self):
        """
        If a user follows and unfollows a moogt then it should delete the notification created
        """
        user = create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(opposition.notifications.filter(
            type=NOTIFICATION_TYPES.moogt_follow).count(), 1)
        self.assertEqual(proposition.notifications.filter(
            type=NOTIFICATION_TYPES.moogt_follow).count(), 1)

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(opposition.notifications.filter(
            type=NOTIFICATION_TYPES.moogt_follow).count(), 0)
        self.assertEqual(proposition.notifications.filter(
            type=NOTIFICATION_TYPES.moogt_follow).count(), 0)

    def test_is_following_field_of_moogt_serializer_should_be_set_properly(self):
        """
        If a person is following is a moogt is_following should be set to True,
        otherwise it should be False
        """
        create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_following'])

        response = self.post(moogt.id)
        self.assertFalse(response.data['is_following'])

    def test_latest_read_at_position_should_be_set_properly(self):
        """
        If a person is following this moogt latest_read_at should not be None
        """
        create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['latest_read_at'])

    def test_following_a_moogt_updates_last_opened_following_field(self):
        """
        If a person follows a moogt it should update the last opened following field
        to the moogt it just followed
        """
        user = create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")
        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)

        user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(user.last_opened_following_moogt, moogt)

    def test_following_a_moogt_while_you_have_blocked_everyone(self):
        """Should not be able to follow a moogt while you've blocked everyone in the moogt."""
        user = create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")

        BlockingFactory.create(user=user, blocked_user=proposition)
        BlockingFactory.create(user=user, blocked_user=opposition)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        moderator = create_user('moderator', 'password')
        BlockingFactory.create(user=user, blocked_user=moderator)
        moogt.set_moderator(moderator)
        moogt.save()

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_following_a_moogt_while_you_have_blocked_some_of_the_moogters(self):
        """Should be able to follow a moogt while you have blocked some of the moogters."""
        user = create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")

        BlockingFactory.create(user=user, blocked_user=proposition)
        BlockingFactory.create(user=user, blocked_user=opposition)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        moderator = create_user('moderator', 'password')
        moogt.set_moderator(moderator)
        moogt.save()

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_following_a_moogt_while_you_have_been_blocked_by_everyone_in_the_moogt(self):
        """Should not be able to follow a moogt while being blocked by everyone in the moogt."""
        user = create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")

        BlockingFactory.create(blocked_user=user, user=proposition)
        BlockingFactory.create(blocked_user=user, user=opposition)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        moderator = create_user('moderator', 'password')
        BlockingFactory.create(blocked_user=user, user=moderator)
        moogt.set_moderator(moderator)
        moogt.save()

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_following_a_moogt_with_moderator_while_you_have_been_blocked_by_some_of_the_participants(self):
        """It should be possible to follow a moogt while you have been blocked by some of the participants."""
        user = create_user_and_login(self)

        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")

        BlockingFactory.create(blocked_user=user, user=proposition)
        BlockingFactory.create(blocked_user=user, user=opposition)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=1)
        moderator = create_user('moderator', 'password')
        moogt.set_moderator(moderator)
        moogt.save()

        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class MyMoogtListApiViewTests(APITestCase):
    def get(self):
        url = reverse('api:moogts:my_moogt_list', kwargs={'version': 'v1'})
        return self.client.get(url)

    def test_success(self):
        """
        Successfully retrieve Moogts Created by the user
        """
        opposition_user = create_user("test_user1", "test_password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user, resolution="moogt resolution 1",
                                       opposition=opposition_user,
                                       started_at_days_ago=1)
        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"]
                         [0]["proposition_id"], user.id)

    def test_opposing_moogts(self):
        """
        If a user is an opposer on a Moogt retrieve that moogt
        """
        proposition_user = create_user("test_user1", "test_password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user, resolution="moogt resolution 1",
                                       opposition=user,
                                       started_at_days_ago=1)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["opposition_id"], user.id)

    def test_neither_opposing_nor_proposing(self):
        """
        If a user is neither opposing nor proposing on a moogt the moogt should not be retrieved
        """
        proposition_user = create_user("test_user1", "test_password")
        opposition_user = create_user("test_user2", "test_password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user, resolution="moogt resolution 1",
                                       opposition=opposition_user,
                                       started_at_days_ago=1)
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_ended_moogt(self):
        """
        If a moogt has ended it should not be retrieved
        """
        proposition_user = create_user("test_user1", "test_password")
        opposition_user = create_user("test_user2", "test_password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user, resolution="moogt resolution 1",
                                       opposition=opposition_user,
                                       has_ended=True)
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_no_owned_moogt(self):
        """
        If a user is not participating in any moogt it should retrieve nothing
        """
        user = create_user_and_login(self)
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_sorting_my_moogts(self):
        """
        Moogts should be sorted based on the last argument added
        """
        opposition_user = create_user("test_user1", "test_password")
        user = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(user, resolution="moogt resolution 1",
                                              opposition=opposition_user,
                                              started_at_days_ago=1)

        moogt2: Moogt = create_moogt_with_user(user, resolution="moogt resolution 2",
                                               opposition=opposition_user,
                                               started_at_days_ago=1)

        create_argument(moogt=moogt, argument='argument 1',
                        user=opposition_user)
        create_argument(moogt=moogt2, argument='argument 2',
                        user=opposition_user)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], moogt2.pk)
        self.assertEqual(response.data['results'][1]['id'], moogt.pk)

        create_argument(moogt=moogt, argument='argument 3',
                        user=opposition_user)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], moogt.pk)
        self.assertEqual(response.data['results'][1]['id'], moogt2.pk)

    def test_premiering_moogts_are_included(self):
        opposition_user = create_user("test_user1", "test_password")
        user = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(
            user, resolution="moogt resolution 1", opposition=opposition_user)
        moogt.premiering_date = timezone.now() + timedelta(days=1)
        moogt.is_premiering = True
        moogt.save()

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], moogt.id)
        self.assertEqual(response.data['results']
                         [0]['is_premiering_moogt'], True)


class LastOpenedMooogtApiViewTests(APITestCase):
    def get(self, following="false"):
        url = reverse('api:moogts:last_opened_moogt', kwargs={
                      'version': 'v1'}) + f'?following={following}'
        return self.client.get(url)

    def test_success(self):
        """
        If a user successfully views a moogt then it should return the last opened moogt to the user
        """
        proposition_user = create_user("test_user1", "test_password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user, resolution="moogt resolution 1",
                                       opposition=user,
                                       has_ended=True,
                                       started_at_days_ago=1)
        user.last_opened_moogt = moogt
        user.save()

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.id, response.data['id'])

    def test_no_opened_moogts(self):
        """
        If a user has never opened a moogt then it should return an empty moogt
        """
        user = create_user_and_login(self)
        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, None)

    def test_only_pending_activities_should_be_attached_with_moogt(self):
        """only activities which are pending should come attached with a moogt"""
        proposition_user = create_user("test_user1", "test_password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user, resolution="moogt resolution 1",
                                       opposition=user,
                                       has_ended=True,
                                       started_at_days_ago=1)
        user.last_opened_moogt = moogt
        user.save()

        moogt_activity = MoogtActivity.objects.create(moogt=moogt,
                                                      type=MoogtActivityType.CARD_REQUEST.value,
                                                      status=ActivityStatus.ACCEPTED.value)

        moogt_activity_2 = MoogtActivity.objects.create(moogt=moogt,
                                                        type=MoogtActivityType.PAUSE_REQUEST.value,
                                                        status=ActivityStatus.DECLINED.value)

        moogt_activity_3 = MoogtActivity.objects.create(moogt=moogt,
                                                        type=MoogtActivityType.END_REQUEST.value,
                                                        status=ActivityStatus.EXPIRED.value)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['activities']), 0)


class UpdateMoogtPublicityStatusViewTest(APITestCase):
    def post(self, body):
        url = reverse('api:moogts:update_moogt_publicity',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format="json")

    def test_successfully_update_moogt(self):
        """
        Test successfully update publicity status
        """

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution", )
        response = self.post({"moogt_id": moogt.id,
                              "visibility": Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["visibility"],
                         Visibility.FOLLOWERS_ONLY.name)

    def test_non_existent_moogt(self):
        """
        Test updating publicity status of a non existent moogt
        """
        user = create_user_and_login(self)
        response = self.post({"moogt_id": 1,
                              "visibility": Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_status(self):
        """
        Test Updating publicity status with an invalid status
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution", )

        response = self.post({"moogt_id": moogt.id,
                              "visibility": "Invalid status"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FollowingMoogtListViewTest(APITestCase):
    def get(self):
        url = reverse('api:moogts:following_moogt_list',
                      kwargs={'version': 'v1'})
        return self.client.get(url)

    def test_success(self):
        user = create_user_and_login(self)

        user_1 = create_user("username", "password")
        moogt = create_moogt_with_user(user_1, resolution="test resolution")
        moogt.followers.add(user)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], moogt.id)

    def test_following_moogt_sorting(self):
        """
        Test following moogt sorting based on the number of the unread cards count
        """
        user = create_user_and_login(self)
        prop = create_user("proposition", "password")
        opp = create_user("opposition", "password")

        moogt = create_moogt_with_user(
            prop, opposition=opp, resolution="test resolution", started_at_days_ago=1)
        moogt2 = create_moogt_with_user(
            prop, opposition=opp, resolution="test resolution 2", started_at_days_ago=1)

        moogt.followers.add(user)
        moogt2.followers.add(user)

        read_by = ReadBy.objects.create(
            user=user, moogt=moogt, latest_read_at=timezone.now())
        read_by2 = ReadBy.objects.create(
            user=user, moogt=moogt2, latest_read_at=timezone.now())

        # create two unread arguments for first moogt
        for i in range(3):
            create_argument(moogt=moogt2, argument='argument 1', user=prop)

        # create one unread argument for second moogt
        for i in range(2):
            create_argument(moogt=moogt, argument='argument 2', user=opp)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], moogt2.pk)
        self.assertEqual(response.data['results'][1]['id'], moogt.pk)

        for i in range(2):
            create_argument(moogt=moogt, argument='argument 3', user=prop)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], moogt.pk)
        self.assertEqual(response.data['results'][1]['id'], moogt2.pk)


class EndMoogtViewTests(APITestCase):
    def post(self, moogt_id, end_request_status=None):
        url = reverse('api:moogts:end_moogt', kwargs={
                      'version': 'v1', 'pk': moogt_id})
        return self.client.post(url, end_request_status)

    def test_non_existing_moogt(self):
        """
        It should respond with a not found resonse for moogts that don't exist.
        """
        create_user_and_login(self, 'user', 'test_password')
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_trying_to_end_a_moogt(self):
        """
        A user who is not authenticated, should not be able to perform any actions.
        It should respond with unauthorized response.
        """
        user = create_user('test_user', 'test_password')
        moogt = create_moogt_with_user(user)
        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_participant_trying_to_end_a_moogt(self):
        """
        A non participant of the moogt should not be allowed to perform any actions.
        """
        proposition_user = create_user('pro', 'test_password')
        moogt = create_moogt_with_user(proposition_user, opposition=True)
        create_user_and_login(self, 'user', 'test_password')
        response = self.post(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_proposition_trying_to_end_a_moogt(self):
        """
        If a proposition user tries to end the moogt, it should update the moogt appropriately.
        """
        user = create_user_and_login(self, 'pro', 'test_password')
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)
        response = self.post(moogt.id, {'status': MoogtEndStatus.concede()})
        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(moogt.get_end_requested())
        self.assertTrue(moogt.get_end_requested_by_proposition())
        self.assertEqual(moogt.get_end_request_status(),
                         MoogtEndStatus.concede())
        self.assertTrue(moogt.get_has_ended())

    def test_opposition_trying_to_end_a_moogt(self):
        """
        If an opposition user tries to end the moogt, it should update the moogt appropriately.
        """
        proposition_user = create_user('prop', 'test_password')
        opposition_user = create_user_and_login(self, 'opp', 'test_password')
        moogt = create_moogt_with_user(
            proposition_user, opposition=opposition_user, started_at_days_ago=0)

        response = self.post(moogt.id, {'status': MoogtEndStatus.concede()})
        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(moogt.get_end_requested())
        self.assertFalse(moogt.get_end_requested_by_proposition())
        self.assertEqual(moogt.get_end_request_status(),
                         MoogtEndStatus.concede())
        self.assertTrue(moogt.get_has_ended())


class MoogtSuggestionViewTests(APITestCase):
    def post(self, data):
        url = reverse('api:moogts:create_moogt_suggestion',
                      kwargs={'version': 'v1'})
        return self.client.post(url, data, format="json")

    def test_without_providing_a_moogt_id(self):
        """
        If a related moogt is not provided in the request, it should respond with a bad request
        response.
        """
        create_user_and_login(self)
        response = self.post({'moderator': 1})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_successfully_suggest_moderator(self):
        """
        If an existing moderator is passed it should should create the suggestion accordingly
        """
        moderator = create_user("mod", 'test_password')
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'moderator': moderator.id}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MoogtMiniSuggestion.objects.first().get_type(), 'moderator')

    def test_successfully_suggest_resolution(self):
        """
        If an existing resolution is passed it should should create the suggestion accordingly
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'resolution': 'suggested resolution'}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mini_suggestion = MoogtMiniSuggestion.objects.first()
        self.assertEqual(mini_suggestion.get_type(), 'resolution')
        self.assertIsNotNone(mini_suggestion.message)
        self.assertEqual(mini_suggestion.message.summaries.count(), 1)

    def test_successfully_suggest_duration(self):
        """
        If an existing duration is passed it should should create the suggestion accordingly
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'max_duration': timezone.timedelta(days=5)}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MoogtMiniSuggestion.objects.first().get_type(), 'max_duration')

    def test_successfully_suggest_reply_time(self):
        """
        If an existing reply time is passed it should should create the suggestion accordingly
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [{'idle_timeout_duration': timezone.timedelta(hours=1)}]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MoogtMiniSuggestion.objects.first(
        ).get_type(), 'idle_timeout_duration')

    def test_successfully_suggest_visibility(self):
        """
        If an existing visibility is passed it should should create the suggestion accordingly
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'visibility': Visibility.FOLLOWERS_ONLY.name}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MoogtMiniSuggestion.objects.first().get_type(), 'visibility')

    def test_successfully_suggest_description(self):
        """
        If an existing description is passed it should should create the suggestion accordingly
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'description': 'suggested description'}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MoogtMiniSuggestion.objects.first().get_type(), 'description')

    def test_sending_two_suggestions(self):
        """
        test if two suggestions are sent it should create two suggestions
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'resolution': 'suggested resolution'},
                                  {'description': 'suggested description'}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MoogtMiniSuggestion.objects.count(), 2)

    def test_sending_non_existing_moogt(self):
        """
        test if non existing moogt is sent it should respond with a moogt not found
        """
        proposition_user = create_user_and_login(self)

        response = self.post(
            {'moogt': 1, 'resolution': 'suggested resolution'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(MoogtMiniSuggestion.objects.count(), 0)

    def test_suggesting_non_existing_user_as_a_moderator(self):
        """
        test if non existing user is sent to be a moderator it should respond with a user not found
        """
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'moderator': proposition_user.pk + 5}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(MoogtMiniSuggestion.objects.count(), 0)

    def test_send_max_duration_and_idle_timeout_duration(self):
        """
        If both max_duration_and_idle_timeout_duration values are set a mini suggestion should be created.
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'max_duration': moogt.get_max_duration(),
                                   'idle_timeout_duration': moogt.get_idle_timeout_duration()}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(moogt.mini_suggestions.count(), 1)

    def test_suggest_premiering_date(self):
        """Test suggesting premiering date for a moogt."""
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)
        premiering_date = timezone.now()
        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'premiering_date': premiering_date}
                              ]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(moogt.mini_suggestions.count(), 1)
        mini_suggestion: MoogtMiniSuggestion = moogt.mini_suggestions.first()
        self.assertEqual(mini_suggestion.premiering_date, premiering_date)
        self.assertEqual(mini_suggestion.get_type(), 'premiering_date')

    def test_edit_a_mini_suggestion(self):
        """
        If a mini suggestion exists it should be linked to the child.
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, resolution='test resolution')

        suggester = create_user('suggester', 'pass123')
        mini_suggestion = create_mini_suggestion(
            moogt=moogt, resolution='test', suggester=suggester)
        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'resolution': 'new test'}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mini_suggestion.refresh_from_db()
        self.assertEqual(mini_suggestion.state,
                         MiniSuggestionState.EDITED.value)
        self.assertEqual(mini_suggestion.message.summaries.filter(
            verb=MessageSummary.VERBS.EDIT.value).count(), 1)
        self.assertIsNotNone(mini_suggestion.suggested_child)

    def test_send_tags_as_a_mini_suggestion(self):
        """
        Tags should be created as a mini suggestion.
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'tags': [{'name': 'tag 1'}]}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Tag.objects.count(), 1)

    def test_send_invalid_suggestion(self):
        """You can't make a suggestion for two settings at the same time, unless, you're suggesting a duration"""
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'resolution': 'suggested resolution',
                                      'tags': [{'name': 'tag 1'}]}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stop_countdown_timer(self):
        """If the moogt is premiering in the future, it should create a suggestion to stop the timer."""
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)
        moogt.premiering_date = timezone.now()
        moogt.save()

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'stop_countdown': True}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mini_suggestion: MoogtMiniSuggestion = moogt.mini_suggestions.first()
        self.assertEqual(mini_suggestion.stop_countdown, True)
        self.assertEqual(mini_suggestion.get_type(), 'stop_countdown')

    def test_send_banner_suggestion(self):
        """Banner should be created as a mini suggestion"""
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)
        banner = MoogtBanner.objects.create()

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'banner': banner.id}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mini_suggestion: MoogtMiniSuggestion = moogt.mini_suggestions.first()
        self.assertEqual(mini_suggestion.banner.id, banner.id)
        self.assertEqual(mini_suggestion.get_type(), 'banner')

    def test_edit_banner_suggestion(self):
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)
        banner = MoogtBanner.objects.create()
        original_suggestion = MoogtMiniSuggestion.objects.create(
            moogt=moogt, banner=banner, user=proposition_user)
        banner = MoogtBanner.objects.create()

        self.client.force_login(moogt.get_opposition())
        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'banner': banner.id}
                              ]})

        original_suggestion.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(original_suggestion.state,
                         MiniSuggestionState.EDITED.value)
        self.assertEqual(MoogtMiniSuggestion.objects.count(), 2)

    def test_send_banner_with_non_existent_banner(self):
        """Non existent banner id should fail creating a minisuggestion"""
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'banner': 1}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_suggest_removing_a_banner(self):
        """Banner should be able to be suggested to be removed"""
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)
        banner = MoogtBanner.objects.create()
        moogt.banner = banner
        moogt.save()

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'remove_banner': True}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mini_suggestion: MoogtMiniSuggestion = moogt.mini_suggestions.first()
        self.assertEqual(mini_suggestion.get_type(), 'remove_banner')

    def test_suggest_removing_a_banner_on_a_moogt_with_no_banner(self):
        """Banner should not be able to be suggested to be removed if the moogt has no banner"""
        proposition_user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            proposition_user, opposition=True, started_at_days_ago=0)

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'remove_banner': True}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_suggest_premiering_date_twice(self):
        """
        Multiple mini suggestion of the same type should not be created
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, started_at_days_ago=0)
        premiering_date = timezone.now()

        response = self.post({'moogt': moogt.id,
                              'changes': [
                                  {'premiering_date': premiering_date}
                              ]})

        response = self.post({'moogt': moogt.pk,
                              'changes': [
                                  {'premiering_date': premiering_date}
                              ]})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(moogt.mini_suggestions.count(), 1)


class MoogtSuggestionActionApiViewTests(APITestCase):
    def post(self, data):
        url = reverse('api:moogts:update_moogt_suggestion',
                      kwargs={'version': 'v1'})
        return self.client.post(url, data, format="json")

    def test_approve_resolution_suggestion(self):
        """
        """
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, resolution="test suggested resolution")

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(suggestion.moogt.resolution,
                         'test suggested resolution')
        self.assertEqual(suggestion.state, MiniSuggestionState.APPROVED.value)
        self.assertEqual(suggestion.message.summaries.filter(
            verb=MessageSummary.VERBS.APPROVE.value).count(), 1)
        self.assertEqual(opposition.notifications.filter(
            verb="approved suggestion").count(), 1)
        self.assertEqual(opposition.notifications.filter(
            verb="approved suggestion").first().target, suggestion)

    def test_disapprove_resolution_suggestion(self):
        """
        """
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition, resolution='test resolution', opposition=opposition,
                                       started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, resolution="test suggested resolution")

        response = self.post(
            {'action': MiniSuggestionState.DISAPPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()
        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.resolution, 'test resolution')
        self.assertEqual(suggestion.state,
                         MiniSuggestionState.DISAPPROVED.value)
        self.assertEqual(suggestion.message.summaries.filter(
            verb=MessageSummary.VERBS.DECLINE.value).count(), 1)

    def test_approve_moderator_suggestion(self):
        """
        """
        opposition = create_user("username", 'test_password')
        moderator = create_user("username1", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, moderator=moderator, )

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(suggestion.moogt.moderator, moderator)
        self.assertEqual(suggestion.state, MiniSuggestionState.APPROVED.value)

    def test_approve_max_duration(self):
        """
        """
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, max_duration=timezone.timedelta(days=5))

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(suggestion.moogt.max_duration,
                         timezone.timedelta(days=5))
        self.assertEqual(suggestion.state, MiniSuggestionState.APPROVED.value)

    def test_approve_visibility(self):
        """
        """
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, visiblity=Visibility.FOLLOWERS_ONLY.value)

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(suggestion.moogt.visibility,
                         Visibility.FOLLOWERS_ONLY.value)
        self.assertEqual(suggestion.state, MiniSuggestionState.APPROVED.value)

    def test_approve_reply_time(self):
        """
        """
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, idle_timeout_duration=timezone.timedelta(hours=1))

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(suggestion.moogt.idle_timeout_duration,
                         timezone.timedelta(hours=1))
        self.assertEqual(suggestion.state, MiniSuggestionState.APPROVED.value)

    def test_approve_description(self):
        """
        """
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = create_mini_suggestion(
            moogt, opposition, description='suggested description')

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})

        suggestion.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(suggestion.moogt.description, 'suggested description')
        self.assertEqual(suggestion.state, MiniSuggestionState.APPROVED.value)

    def test_approve_premiering_date(self):
        """If there is a suggestion for premiering date it should be approved if suggested user wants to approve."""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt,
                                                        user=opposition,
                                                        premiering_date=timezone.now())

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        suggestion.refresh_from_db()
        self.assertIsNotNone(suggestion.moogt.premiering_date)
        self.assertTrue(suggestion.moogt.is_premiering)
        self.assertEqual(opposition.notifications.filter(
            verb="premiering").count(), 1)
        self.assertEqual(opposition.notifications.filter(
            verb="premiering").first().target, moogt)

    def test_approve_stop_countdown_suggestion(self):
        """If a mini suggestion for stopping a countdown exists, it should be a suggestion that could be approved."""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        moogt.premiering_date = timezone.now()
        moogt.save()
        suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt,
                                                        user=opposition,
                                                        stop_countdown=True)
        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moogt.refresh_from_db()
        self.assertIsNone(moogt.premiering_date)

    def test_cancel_stop_countdown_suggestion(self):
        """If a mini suggestion for stopping a countdown exists, it should be a suggestion that could be cancelled."""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        moogt.premiering_date = timezone.now()
        moogt.save()
        suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt,
                                                        user=opposition,
                                                        stop_countdown=True)
        response = self.post(
            {'action': MiniSuggestionState.CANCEL.value, 'suggestion_id': suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moogt.refresh_from_db()
        self.assertIsNotNone(moogt.premiering_date)

    def test_approve_remove_banner_suggestion(self):
        """If a mini suggestion for removing a banner exists it should be a suggestion that could be approved"""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        moogt.banner = MoogtBanner.objects.create()
        moogt.save()

        suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt,
                                                        user=opposition,
                                                        remove_banner=True)

        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moogt.refresh_from_db()
        self.assertIsNone(moogt.banner)

    def test_cancel_remove_banner_suggestion(self):
        """If a mini suggestion for removing a banner exists it should be a suggestion that could be cancelled"""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt: Moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        moogt.banner = MoogtBanner.objects.create()
        moogt.save()

        suggestion = MoogtMiniSuggestion.objects.create(moogt=moogt,
                                                        user=opposition,
                                                        remove_banner=True)

        response = self.post(
            {'action': MiniSuggestionState.CANCEL.value, 'suggestion_id': suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moogt.refresh_from_db()
        self.assertIsNotNone(moogt.banner)

    def test_approve_tags_suggestion(self):
        """Tags suggestion should be approved."""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        mini_suggestion = create_mini_suggestion(moogt, opposition)
        tag = Tag.objects.create(name='tag1')
        mini_suggestion.tags.add(tag)
        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value, 'suggestion_id': mini_suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mini_suggestion.refresh_from_db()
        self.assertEqual(mini_suggestion.state,
                         MiniSuggestionState.APPROVED.value)
        moogt.refresh_from_db()
        self.assertEqual(moogt.tags.count(), 1)

    def test_cancel_tags_suggestion(self):
        """Tags suggestion should be canceleable."""
        opposition = create_user("username", 'test_password')
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition, opposition=opposition, started_at_days_ago=0)
        mini_suggestion = create_mini_suggestion(moogt, opposition)
        tag = Tag.objects.create(name='tag1')
        mini_suggestion.tags.add(tag)
        response = self.post(
            {'action': MiniSuggestionState.CANCEL.value, 'suggestion_id': mini_suggestion.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mini_suggestion.refresh_from_db()
        self.assertEqual(mini_suggestion.state,
                         MiniSuggestionState.CANCEL.value)
        self.assertEqual(mini_suggestion.message.summaries.filter(
            verb=MessageSummary.VERBS.CANCEL.value).count(), 1)


class MoogtSuggestionListApiViewTests(APITestCase):
    def get(self, pk):
        url = reverse('api:moogts:list_moogt_suggestion',
                      kwargs={'version': 'v1', 'pk': pk})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt('test resolution 1')
        self.invitee = create_user('invitee', 'pass123')
        create_invitation(inviter=self.user,
                          invitee=self.invitee,
                          moogt=self.moogt)
        self.mini_suggestion = MoogtMiniSuggestion.objects.create(resolution='test resolution',
                                                                  moogt=self.moogt,
                                                                  user=self.user)

    def test_non_authenticated_user(self):
        """
        Non-authenticated user should get a non-authorized response.
        """
        self.client.logout()
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gets_list_of_mini_suggestions(self):
        """
        Gets a list of mini suggestions.
        """
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], 1)

    def test_a_with_non_existing_moogt(self):
        """
        Should respond with a 404 response if the moogt doesn't exist
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_no_mini_suggestions(self):
        """
        It should only get mini suggestions for a particular moogt.
        """
        moogt = create_moogt(resolution='test resolution')
        response = self.get(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


class UploadBannerApiView(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def tearDown(self) -> None:
        if os.path.exists(MEDIA_ROOT):
            for filename in os.listdir(MEDIA_ROOT):
                file_path = os.path.join(MEDIA_ROOT, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except:
                    pass

    def post(self, data):
        url = reverse('api:moogts:upload_banner', kwargs={'version': 'v1'})
        return self.client.post(url, data)

    def test_non_authenticated_user(self):
        """A non authenticated user is not allowed to upload a banner."""
        self.client.logout()
        response = self.post(None)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_a_file(self):
        """Upload a file successfully, it should respond with a 2xx response."""
        banner = generate_photo_file()
        response = self.post({'banner': banner})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data['id'])
        self.assertIsNotNone(response.data['banner'])

    def test_upload_image_validate_min_image_width_height(self):
        """If the image's width and height is below the minimum requirement, it should respond with bad request."""
        banner = generate_photo_file(100, 100)
        response = self.post({'banner': banner})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_image_with_invalid_aspect_ratio(self):
        """If the image's aspect ratio does not meet the requirements, it should respond with a bad request."""
        banner = generate_photo_file(640, 110)
        response = self.post({'banner': banner})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UpdateMoogtApiViewTests(APITestCase):

    def setUp(self) -> None:
        create_user_and_login(self)
        self.moogt = create_moogt()

    def post(self, body):
        url = reverse('api:moogts:update_moogt', kwargs={
                      'version': 'v1', 'pk': self.moogt.id})
        return self.client.post(url, body, format='json')

    def test_update_premiere_date(self):
        """Update the premiering date of a moogt."""
        premiere_date = timezone.now()
        response = self.post({'premiering_date': premiere_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.premiering_date, premiere_date)


class UpdateAllSuggestionsApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.suggester = create_user('suggester', 'pass123')
        self.moogt = create_moogt_with_user(
            self.user, opposition=self.suggester)
        self.invitation = Invitation(
            moogt=self.moogt, invitee=self.suggester, inviter=self.user)
        self.invitation.save()
        self.mini_suggestions_1 = create_mini_suggestion(self.moogt, self.user)
        self.mini_suggestions_2 = create_mini_suggestion(self.moogt, self.user)
        self.mini_suggestions_3 = create_mini_suggestion(
            self.moogt, self.suggester)
        self.mini_suggestions_3 = create_mini_suggestion(
            self.moogt, self.suggester)

    def post(self, body, pk):
        url = reverse('api:moogts:update_all_moogt_suggestion',
                      kwargs={'version': 'v1', 'pk': pk})
        return self.client.post(url, body)

    def test_non_authorized_user(self):
        """A non authorized user should get a not authorized response."""
        self.client.logout()
        response = self.post(None, self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """It should respond with a not found response for a moogt that doesn't exist."""
        response = self.post(None, 404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_no_mini_suggestions(self):
        """If there a no pending mini suggestions for the moogt, it should respond with a bad request response."""
        moogt = create_moogt_with_user(self.user, opposition=self.suggester)
        response = self.post(None, moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        mini_suggestion = create_mini_suggestion(moogt, self.user)
        mini_suggestion.state = MiniSuggestionState.APPROVED.value
        mini_suggestion.save()
        response = self.post(None, moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_approve_action(self):
        """If there are pending mini suggestions and the actions is approve, then they should be approved."""
        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value}, self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMiniSuggestion.objects.filter(
            state=MiniSuggestionState.PENDING.value).count(), 2)
        self.assertEqual(MoogtMiniSuggestion.objects.filter(
            state=MiniSuggestionState.APPROVED.value).count(), 2)

    def test_trying_to_approve_your_own_suggestions(self):
        """
        If you're trying to approve all suggestions but all are by you,
        then a bad request response must be returned.
        """
        moogt = create_moogt_with_user(self.user, opposition=self.suggester)
        create_mini_suggestion(moogt, self.user)
        response = self.post(
            {'action': MiniSuggestionState.APPROVED.value}, moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_cancel_action(self):
        """If there are pending mini suggestions and the actions is approve, then they should be approved."""
        response = self.post(
            {'action': MiniSuggestionState.CANCEL.value}, self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtMiniSuggestion.objects.filter(
            state=MiniSuggestionState.PENDING.value).count(), 2)
        self.assertEqual(MoogtMiniSuggestion.objects.filter(
            state=MiniSuggestionState.CANCEL.value).count(), 2)


class MakeCardRequestApiViewTests(APITestCase):
    def post(self, moogt_id):
        url = reverse('api:moogts:request_card', kwargs={
                      'version': 'v1', 'pk': moogt_id})
        return self.client.post(url)

    def setUp(self):
        self.opposition = create_user("username", "password")
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user, started_at_days_ago=1)

    def test_non_authenticated_user(self):
        """A non authenticated user should be dealt with a 401 response."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """A non existing moogt should be dealt with a 404 response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_opposition_or_proposition(self):
        """Only a moogt participant is allowed to make a request."""
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_current_turn(self):
        """
        Request for card for user who is in turn. Therefore you can't request for card while it's your turn.
        """
        self.moogt.proposition = self.user
        self.moogt.next_turn_proposition = True
        self.moogt.save()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_request(self):
        """Make a request for card successfully."""
        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.next_turn_proposition = False
        self.moogt.save()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, self.user)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.CARD_REQUEST.value)

    def test_if_moderator_is_not_allowed_to_make_request(self):
        """Tests if the moderator is allowed or not to make the card request"""

        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_request_card_twice(self):
        """
        If a moogter requests for extra card twice the second request should fail
        """
        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.next_turn_proposition = False
        self.moogt.save()

        response = self.post(self.moogt.id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)

        response = self.post(self.moogt.id)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)

    def test_successful_request_as_opposition(self):
        """Make a request for card as a opposition."""
        self.moogt.set_opposition(self.user)
        self.moogt.set_proposition(self.opposition)
        self.moogt.set_next_turn_proposition(True)
        self.moogt.save()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, self.user)
        self.assertEqual(self.moogt.activities.first().actor, self.opposition)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.CARD_REQUEST.value)


class CardRequestActionApiViewTests(APITestCase):
    def post(self, activity_id, body=None):
        url = reverse('api:moogts:card_request_action', kwargs={
                      'version': 'v1', 'pk': activity_id})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user)
        self.moogt_activity = MoogtActivity.objects.create(moogt=self.moogt,
                                                           type=MoogtActivityType.CARD_REQUEST.value,
                                                           user=self.user)

    def test_non_authenticated_user(self):
        """Non authenticated is not allowed to perform actions."""
        self.client.logout()
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_activity(self):
        """It should respond with a not found response if the activity doesn't exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_not_providing_status(self):
        """If the status is not provided, it should respond with bad request."""
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request(self):
        """If the status is approve, it should update the moogt."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_next_turn_proposition(False)
        self.moogt.set_last_posted_by_proposition(True)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_next_turn_proposition(), True)
        self.assertEqual(self.moogt.get_last_posted_by_proposition(), False)
        time_diff = timezone.now() - self.moogt.get_latest_argument_added_at()
        self.assertAlmostEqual(time_diff.total_seconds(), 0, delta=0.055)
        argument = Argument.objects.filter(type=ArgumentType.WAIVED.name)
        self.assertTrue(argument.exists())
        self.assertEqual(argument.first().type, ArgumentType.WAIVED.name)
        self.assertEqual(argument.first().user, opposition)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.approve)

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_decline_request_without_moderator(self):
        """Declines the request, should update the activity state to DECLINED"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_decline_request_after_waiting(self):
        """The status of waiting should be chaged to decline """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user(username='opp', password='pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_opposition(opposition)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(self.moogt_activity.actions.first().actor, moderator)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(self.moogt.get_opposition())
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value
                             })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.last().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.last(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_cancel_request(self):
        """If the status is cancel, it should update the activity."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

    def test_approve_your_own_request(self):
        """You cannot approve your own request, hence you should get a bad request."""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request_as_a_non_moogter(self):
        """You cannot approve a request on a moogt that you are not participating in"""
        random_user = create_user_and_login(self, 'random_user', 'test123')
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_request_as_a_non_moogter(self):
        """You cannot approve a request on a moogt that you are not participating in"""
        random_user = create_user_and_login(self, 'random_user', 'test123')
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_your_own_request(self):
        """You can cancel your own request, it should update the activity state to CANCELLED"""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

    def test_last_created_status_creates_new_bundle(self):
        """
        If the last created object in a moogt is a status then request action should create
        a new bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 2)
        self.assertEqual(
            MoogtActivityBundle.objects.last().activities.count(), 1)
        self.assertEqual(MoogtActivityBundle.objects.last(
        ).activities.first().pk, self.moogt_activity.pk)

    # def test_last_created_argument_creates_new_bundle(self):
    #     """
    #     If the last created object in a moogt is a status then request action should create
    #     a new bundle
    #     """
    #     opposition = create_user_and_login(self, 'opposition', 'pass123')
    #     self.moogt.set_opposition(opposition)
    #     self.moogt.set_proposition(self.user)
    #     self.moogt.save()

    #     moogt_status = MoogtStatus.objects.create(
    #         moogt=self.moogt, status=MoogtStatus.STATUS.paused)
    #     bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
    #     argument = create_argument(
    #         moogt=self.moogt, argument='test argument', user=self.user)

    #     response = self.post(self.moogt_activity.id, {
    #                          'status': ActivityStatus.DECLINED.value})

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(MoogtActivityBundle.objects.count(), 2)
    #     self.assertEqual(
    #         MoogtActivityBundle.objects.last().activities.count(), 1)
    #     self.assertEqual(MoogtActivityBundle.objects.last(
    #     ).activities.first().pk, self.moogt_activity.pk)

    def test_last_created_bundle_updates_last_bundle(self):
        """
        If the last created object in a moogt is a bundle the request action should add the
        activity in the bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(bundle.activities.count(), 1)
        self.assertEqual(bundle.activities.first().pk, self.moogt_activity.pk)


class MakeEndMoogtRequestApiViewTests(APITestCase):
    def post(self, moogt_id):
        url = reverse('api:moogts:request_end_moogt', kwargs={
                      'version': 'v1', 'pk': moogt_id})
        return self.client.post(url)

    def setUp(self):
        self.user = create_user_and_login(self)
        self.opposition = create_user("opposition", "password")
        self.moogt = create_moogt()

    def test_non_authenticated_user(self):
        """A non authenticated user should be dealt with a 401 response."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """A non existing moogt should be dealt with a 404 response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_opposition_or_proposition(self):
        """Only a moogt participant is allowed to make a request."""
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_request(self):
        """Make a request for end moogt successfully."""
        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_end_requested(), True)
        self.assertEqual(self.moogt.get_end_requested_by_proposition(), True)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.END_REQUEST.value)

    def test_successfull_request_by_moderator(self):
        """test a moderator to make a request for end moogt"""

        moderator = create_user_and_login(self, 'moderator', 'pass123')
        proposition = create_user('proposition', 'pass123')

        self.moogt.moderator = moderator
        self.moogt.opposition = self.opposition
        self.moogt.proposition = proposition

        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_end_requested(), True)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.END_REQUEST.value)

    def test_successful_request_as_opposition(self):
        """Make a request for end moogt as a opposition."""
        self.moogt.set_opposition(self.user)
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_end_requested(), True)
        self.assertEqual(self.moogt.get_end_requested_by_proposition(), False)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.END_REQUEST.value)


class EndMoogtRequestActionApiViewTests(APITestCase):
    def post(self, activity_id, body=None):
        url = reverse('api:moogts:end_moogt_request_action',
                      kwargs={'version': 'v1', 'pk': activity_id})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user)
        self.moogt_activity = MoogtActivity.objects.create(moogt=self.moogt,
                                                           type=MoogtActivityType.END_REQUEST.value,
                                                           user=self.user)

    def test_non_authenticated_user(self):
        """Non authenticated is not allowed to perform actions."""
        self.client.logout()
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_activity(self):
        """It should respond with a not found response if the activity doesn't exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_not_providing_status(self):
        """If the status is not provided, it should respond with bad request."""
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request(self):
        """If the status is approve, it should update the moogt."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_next_turn_proposition(False)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_has_ended(), True)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'ended')

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.approve)

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request_by_moderator(self):
        """If the status is approved by moderator, it should update the moogt."""
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_has_ended(), True)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'ended')

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_decline_request_without_moderator(self):
        """Declines the request, should update the activity state to DECLINED"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_decline_request_after_waiting(self):
        """The status of waiting should be chaged to decline """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user(username='opp', password='pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_opposition(opposition)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(self.moogt_activity.actions.first().actor, moderator)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(self.moogt.get_opposition())
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value
                             })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.last().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.last(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_cancel_request(self):
        """If the status is cancel, it should update the activity."""
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

    def test_approve_your_own_request(self):
        """You cannot approve your own request, hence you should get a bad request."""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_your_own_request(self):
        """You can cancel your own request, it should update the activity state to CANCELLED"""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

    def test_cancel_request_as_a_non_moogter(self):
        """You cannot approve a request on a moogt that you are not participating in"""
        random_user = create_user_and_login(self, 'random_user', 'test123')
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_a_paused_request(self):
        """Approving a pause request should set is_paused to false"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_next_turn_proposition(False)
        self.moogt.set_is_paused(True)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_has_ended(), True)
        self.assertFalse(self.moogt.get_is_paused())

    def test_last_created_status_creates_new_bundle(self):
        """
        If the last created object in a moogt is a status then request action should create
        a new bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 2)
        self.assertEqual(
            MoogtActivityBundle.objects.last().activities.count(), 1)
        self.assertEqual(MoogtActivityBundle.objects.last(
        ).activities.first().pk, self.moogt_activity.pk)

    # def test_last_created_argument_creates_new_bundle(self):
    #     """
    #     If the last created object in a moogt is a status then request action should create
    #     a new bundle
    #     """
    #     opposition = create_user_and_login(self, 'opposition', 'pass123')
    #     self.moogt.set_opposition(opposition)
    #     self.moogt.set_proposition(self.user)
    #     self.moogt.save()

    #     moogt_status = MoogtStatus.objects.create(
    #         moogt=self.moogt, status=MoogtStatus.STATUS.paused)
    #     bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
    #     argument = create_argument(
    #         moogt=self.moogt, argument='test argument', user=self.user)

    #     response = self.post(self.moogt_activity.id, {
    #                          'status': ActivityStatus.DECLINED.value})

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(MoogtActivityBundle.objects.count(), 2)
    #     self.assertEqual(
    #         MoogtActivityBundle.objects.last().activities.count(), 1)
    #     self.assertEqual(MoogtActivityBundle.objects.last(
    #     ).activities.first().pk, self.moogt_activity.pk)

    def test_last_created_bundle_updates_last_bundle(self):
        """
        If the last created object in a moogt is a bundle the request action should add the
        activity in the bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(bundle.activities.count(), 1)
        self.assertEqual(bundle.activities.first().pk, self.moogt_activity.pk)


class MakePauseMoogtRequestApiViewTests(APITestCase):
    def post(self, moogt_id):
        url = reverse('api:moogts:request_pause_moogt',
                      kwargs={'version': 'v1', 'pk': moogt_id})
        return self.client.post(url)

    def setUp(self):
        self.user = create_user_and_login(self)
        self.opposition = create_user('opposition', 'password')
        self.moogt = create_moogt()

    def test_non_authenticated_user(self):
        """A non authenticated user should be dealt with a 401 response."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """A non existing moogt should be dealt with a 404 response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_opposition_or_proposition(self):
        """Only a moogt participant is allowed to make a request."""
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_request(self):
        """Make a request to pause successfully."""
        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, self.user)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.PAUSE_REQUEST.value)

    def test_successful_request_by_moderator(self):
        """Make a request by a moderator to pause successfully."""
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        proposition = create_user('proposition', 'pass123')

        self.moogt.moderator = moderator
        self.moogt.opposition = self.opposition
        self.moogt.proposition = proposition

        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, moderator)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.PAUSE_REQUEST.value)


class PauseMoogtRequestActionApiViewTests(APITestCase):
    def post(self, activity_id, body=None):
        url = reverse('api:moogts:pause_moogt_request_action',
                      kwargs={'version': 'v1', 'pk': activity_id})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user, started_at_days_ago=1)
        self.moogt_activity = MoogtActivity.objects.create(moogt=self.moogt,
                                                           type=MoogtActivityType.PAUSE_REQUEST.value,
                                                           user=self.user)

    def test_non_authenticated_user(self):
        """Non authenticated is not allowed to perform actions."""
        self.client.logout()
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_activity(self):
        """It should respond with a not found response if the activity doesn't exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_not_providing_status(self):
        """If the status is not provided, it should respond with bad request."""
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request(self):
        """If the status is approve, it should update the moogt and it should create a moogt paused argument"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_is_paused(), True)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        self.assertEqual(self.moogt.statuses.count(), 1)
        self.assertEqual(self.moogt.statuses.first().status,
                         MoogtStatus.STATUS.paused)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'paused')
        self.assertEqual(self.user.notifications.first(
        ).data['data']['moogt']['resolution'], self.moogt.resolution)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.approve)

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request_for_moderator(self):
        """If the status is approved by the moderator, it should update the moogt and it should create a moogt paused status"""
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_is_paused(), True)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        self.assertEqual(self.moogt.statuses.count(), 1)
        self.assertEqual(self.moogt.statuses.first().status,
                         MoogtStatus.STATUS.paused)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'paused')
        self.assertEqual(self.user.notifications.first(
        ).data['data']['moogt']['resolution'], self.moogt.resolution)

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_decline_request_without_moderator(self):
        """Declines the request, should update the activity state to DECLINED"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_decline_request_for_moderator(self):
        """
        Returns waiting if there is moderator in a moogt when declining the request,
        then returns the status changes to decline after the other moogter declines         
        """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(create_user('proposition', 'pass123'))
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.WAITING.value)

    def test_approve_request_after_waiting(self):
        """The status of waiting should be chaged to approved after the decline """

        opposition = create_user_and_login(self, 'opp', 'pass123')
        moderator = create_user(username='mod', password='pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        moogt_activity = MoogtActivity.objects.create(moogt=self.moogt,
                                                      type=MoogtActivityType.PAUSE_REQUEST.value,
                                                      user=moderator)
        response = self.post(moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.data['status'], ActivityStatus.WAITING.value)

        self.assertEqual(moogt_activity.actions.first().actor, opposition)
        self.assertEqual(moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(self.moogt.get_proposition())
        response = self.post(moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value
                             })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(response.data['status'],
                         ActivityStatus.ACCEPTED.value)

        self.assertEqual(moogt_activity.actions.last().actor, self.user)
        self.assertEqual(moogt_activity.actions.last(
        ).action_type, AbstractActivityAction.ACTION_TYPES.approve)

    def test_decline_request_after_waiting(self):
        """The status of waiting should be chaged to decline """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user(username='opp', password='pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_opposition(opposition)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(self.moogt_activity.actions.first().actor, moderator)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(self.moogt.get_opposition())
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value
                             })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.last().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.last(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_cancel_request(self):
        """If the status is cancel, it should update the activity and it should not created a moogt paused argument"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.CANCELLED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)
        self.assertEqual(self.moogt.arguments.count(), 0)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.cancel)

    def test_approve_your_own_request(self):
        """You cannot approve your own request, hence you should get a bad request."""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_your_own_request(self):
        """You can cancel your own request, it should update the activity state to CANCELLED"""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

    def test_cancel_request_as_a_non_moogter(self):
        """You cannot approve a request on a moogt that you are not participating in"""
        random_user = create_user_and_login(self, 'random_user', 'test123')
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_last_created_status_creates_new_bundle(self):
        """
        If the last created object in a moogt is a status then request action should create
        a new bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 2)
        self.assertEqual(
            MoogtActivityBundle.objects.last().activities.count(), 1)
        self.assertEqual(MoogtActivityBundle.objects.last(
        ).activities.first().pk, self.moogt_activity.pk)

    # def test_last_created_argument_creates_new_bundle(self):
    #     """
    #     If the last created object in a moogt is a status then request action should create
    #     a new bundle
    #     """
    #     opposition = create_user_and_login(self, 'opposition', 'pass123')
    #     self.moogt.set_opposition(opposition)
    #     self.moogt.set_proposition(self.user)
    #     self.moogt.save()

    #     moogt_status = MoogtStatus.objects.create(
    #         moogt=self.moogt, status=MoogtStatus.STATUS.paused)
    #     bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
    #     argument = create_argument(
    #         moogt=self.moogt, argument='test argument', user=self.user)

    #     response = self.post(self.moogt_activity.id, {
    #                          'status': ActivityStatus.DECLINED.value})

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(MoogtActivityBundle.objects.count(), 2)
    #     self.assertEqual(
    #         MoogtActivityBundle.objects.last().activities.count(), 1)
    #     self.assertEqual(MoogtActivityBundle.objects.last(
    #     ).activities.first().pk, self.moogt_activity.pk)

    def test_last_created_bundle_updates_last_bundle(self):
        """
        If the last created object in a moogt is a bundle the request action should add the
        activity in the bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(bundle.activities.count(), 1)
        self.assertEqual(bundle.activities.first().pk, self.moogt_activity.pk)


class MakeResumeMoogtRequestApiViewTests(APITestCase):
    def post(self, moogt_id):
        url = reverse('api:moogts:request_resume_moogt',
                      kwargs={'version': 'v1', 'pk': moogt_id})
        return self.client.post(url)

    def setUp(self):
        self.user = create_user_and_login(self)
        self.opposition = create_user('opposition', 'password')
        self.moogt = create_moogt()

    def test_non_authenticated_user(self):
        """A non authenticated user should be dealt with a 401 response."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """A non existing moogt should be dealt with a 404 response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_opposition_or_proposition(self):
        """Only a moogt participant is allowed to make a request."""
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_request(self):
        """Make a request to resume successfully."""

        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.is_paused = True
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, self.user)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.RESUME_REQUEST.value)

    def test_successful_request_by_moderator(self):
        """Make a request by a moderator to pause successfully."""

        moderator = create_user_and_login(self, 'moderator', 'pass123')
        proposition = create_user('proposition', 'pass123')

        self.moogt.moderator = moderator
        self.moogt.opposition = self.opposition
        self.moogt.proposition = proposition

        self.moogt.is_paused = True
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, moderator)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.RESUME_REQUEST.value)

    def test_non_paused_moogt(self):
        """A non paused moogt should be dealt with a bad request."""
        self.moogt.proposition = self.user
        self.moogt.is_paused = False
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ResumeMoogtRequestActionApiViewTests(APITestCase):
    def post(self, activity_id, body=None):
        url = reverse('api:moogts:resume_moogt_request_action',
                      kwargs={'version': 'v1', 'pk': activity_id})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user)
        self.moogt_activity = MoogtActivity.objects.create(moogt=self.moogt,
                                                           type=MoogtActivityType.RESUME_REQUEST.value,
                                                           user=self.user)

    def test_non_authenticated_user(self):
        """Non authenticated is not allowed to perform actions."""
        self.client.logout()
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_activity(self):
        """It should respond with a not found response if the activity doesn't exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_not_providing_status(self):
        """If the status is not provided, it should respond with bad request."""
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request(self):
        """If the status is approve, it should update the moogt."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        now = timezone.now()

        self.moogt.set_is_paused(True)
        self.moogt.set_paused_at(now - datetime.timedelta(days=2))
        self.moogt.set_latest_argument_added_at(
            now - datetime.timedelta(days=3))
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_is_paused(), False)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        self.assertEqual(self.moogt.statuses.count(), 1)
        self.assertEqual(self.moogt.statuses.first().status,
                         MoogtStatus.STATUS.resumed)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'resumed')

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.approve)

    def test_approve_request_by_moderator(self):
        """If the status is approved by moderator, it should update the moogt."""
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        now = timezone.now()

        self.moogt.set_is_paused(True)
        self.moogt.set_paused_at(now - datetime.timedelta(days=2))
        self.moogt.set_latest_argument_added_at(
            now - datetime.timedelta(days=3))
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.get_is_paused(), False)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        self.assertEqual(self.moogt.statuses.count(), 1)
        self.assertEqual(self.moogt.statuses.first().status,
                         MoogtStatus.STATUS.resumed)
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'resumed')

    def test_decline_request_without_moderator(self):
        """Declines the request, should update the activity state to DECLINED"""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_decline_request_after_waiting(self):
        """The status of waiting should be chaged to decline """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user(username='opp', password='pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_opposition(opposition)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(self.moogt_activity.actions.first().actor, moderator)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(self.moogt.get_opposition())
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value
                             })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.last().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.last(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_cancel_request(self):
        """If the status is cancel, it should update the activity."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)
        self.assertEqual(self.moogt.arguments.count(), 0)

    def test_moogt_is_not_paused(self):
        """If the moogt is not paused it should return bad request."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_is_paused(False)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.PENDING.value)

    def test_approve_your_own_request(self):
        """You cannot approve your own request, hence you should get a bad request."""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_your_own_request(self):
        """You can cancel your own request, it should update the activity state to CANCELLED"""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

    def test_cancel_request_as_a_non_moogter(self):
        """You cannot approve a request on a moogt that you are not participating in"""
        random_user = create_user_and_login(self, 'random_user', 'test123')
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_last_created_status_creates_new_bundle(self):
        """
        If the last created object in a moogt is a status then request action should create
        a new bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.is_paused = True
        self.moogt.save()

        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 2)
        self.assertEqual(
            MoogtActivityBundle.objects.last().activities.count(), 1)
        self.assertEqual(MoogtActivityBundle.objects.last(
        ).activities.first().pk, self.moogt_activity.pk)

    # def test_last_created_argument_creates_new_bundle(self):
    #     """
    #     If the last created object in a moogt is a status then request action should create
    #     a new bundle
    #     """
    #     opposition = create_user_and_login(self, 'opposition', 'pass123')
    #     self.moogt.set_opposition(opposition)
    #     self.moogt.set_proposition(self.user)
    #     self.moogt.is_paused = True
    #     self.moogt.save()

    #     moogt_status = MoogtStatus.objects.create(
    #         moogt=self.moogt, status=MoogtStatus.STATUS.paused)
    #     bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
    #     argument = create_argument(
    #         moogt=self.moogt, argument='test argument', user=self.user)

    #     response = self.post(self.moogt_activity.id, {
    #                          'status': ActivityStatus.DECLINED.value})

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(MoogtActivityBundle.objects.count(), 2)
    #     self.assertEqual(
    #         MoogtActivityBundle.objects.last().activities.count(), 1)
    #     self.assertEqual(MoogtActivityBundle.objects.last(
    #     ).activities.first().pk, self.moogt_activity.pk)

    def test_last_created_bundle_updates_last_bundle(self):
        """
        If the last created object in a moogt is a bundle the request action should add the
        activity in the bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.is_paused = True
        self.moogt.save()

        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(bundle.activities.count(), 1)
        self.assertEqual(bundle.activities.first().pk, self.moogt_activity.pk)


class MakeDeleteMoogtRequestApiViewTests(APITestCase):
    def post(self, moogt_id):
        url = reverse('api:moogts:request_delete_moogt',
                      kwargs={'version': 'v1', 'pk': moogt_id})
        return self.client.post(url)

    def setUp(self):
        self.user = create_user_and_login(self)
        self.opposition = create_user("opposition", 'password')
        self.moogt = create_moogt()

    def test_non_authenticated_user(self):
        """A non authenticated user should be dealt with a 401 response."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """A non existing moogt should be dealt with a 404 response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_opposition_or_proposition(self):
        """Only a moogt participant is allowed to make a request."""
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_request(self):
        """Make a request to delete moogt successfully."""
        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, self.user)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.DELETE_REQUEST.value)

    def test_successful_request_by_moderator(self):
        """Test a moderator to make a request to delete moogt successfully."""

        moderator = create_user_and_login(self, 'moderator', 'pass123')
        proposition = create_user('proposition', 'pass123')

        self.moogt.moderator = moderator
        self.moogt.opposition = self.opposition
        self.moogt.proposition = proposition

        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.activities.count(), 1)
        self.assertEqual(self.moogt.activities.first().user, moderator)
        self.assertEqual(self.moogt.activities.first().type,
                         MoogtActivityType.DELETE_REQUEST.value)

    def test_make_successive_delete_requests(self):
        """Making a successive delete requests while there is a pending request is not allowed."""
        self.moogt.proposition = self.user
        self.moogt.opposition = self.opposition
        self.moogt.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        delete_activity = self.moogt.activities.first()
        delete_activity.status = ActivityStatus.DECLINED.value
        delete_activity.save()

        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class DeleteMoogtRequestActionApiViewTests(APITestCase):
    def post(self, activity_id, body=None):
        url = reverse('api:moogts:delete_moogt_request_action',
                      kwargs={'version': 'v1', 'pk': activity_id})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user)
        self.argument = create_argument(
            moogt=self.moogt, argument='most applauded', user=self.user)
        self.moogt_activity = MoogtActivity.objects.create(moogt=self.moogt,
                                                           type=MoogtActivityType.DELETE_REQUEST.value,
                                                           user=self.user)
        self.view = create_reaction_view(
            self.user, self.argument, type=ViewType.ARGUMENT_REACTION.name)

    def test_non_authenticated_user(self):
        """Non authenticated is not allowed to perform actions."""
        self.client.logout()
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_activity(self):
        """It should respond with a not found response if the activity doesn't exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_not_providing_status(self):
        """If the status is not provided, it should respond with bad request."""
        response = self.post(self.moogt_activity.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request(self):
        """If the status is approve, it should update the moogt."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.is_removed, True)
        self.assertEqual(self.moogt.arguments.count(), 0)

        self.assertEqual(View.objects.count(), 0)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_request_by_moderator(self):
        """If the status is approved by moderator, it should update the moogt."""
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.is_removed, True)
        self.assertEqual(self.moogt.arguments.count(), 0)

        self.assertEqual(View.objects.count(), 0)

        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.ACCEPTED.value)

        response2 = self.post(self.moogt_activity.id, {
            'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_decline_request_without_moderator(self):
        """Declines the request, should update the activity state to DECLINED"""

        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_decline_request_for_moderator(self):
        """
        Returns waiting if there is moderator in a moogt when declining the request,
        then returns the status changes to decline after the other moogter declines         
        """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(create_user('proposition', 'pass123'))
        self.moogt.set_moderator(moderator)
        self.moogt.save()

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.WAITING.value)

    def test_decline_request_after_waiting(self):
        """The status of waiting should be chaged to decline """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user(username='opp', password='pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_opposition(opposition)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(self.moogt_activity.actions.first().actor, moderator)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(self.moogt.get_opposition())
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value
                             })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.DECLINED.value)

        self.assertEqual(self.moogt_activity.actions.last().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.last(
        ).action_type, AbstractActivityAction.ACTION_TYPES.decline)

    def test_cancel_request(self):
        """If the status is cancel, it should update the activity."""
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.CANCELLED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

        self.assertEqual(self.moogt_activity.actions.first().actor, opposition)
        self.assertEqual(self.moogt_activity.actions.first(
        ).action_type, AbstractActivityAction.ACTION_TYPES.cancel)

    def test_approve_your_own_request(self):
        """You cannot approve your own request, hence you should get a bad request."""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.ACCEPTED.value})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_your_own_request(self):
        """You can cancel your own request, it should update the activity state to CANCELLED"""
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.moogt_activity.refresh_from_db()
        self.assertEqual(self.moogt_activity.status,
                         ActivityStatus.CANCELLED.value)

    def test_cancel_request_as_a_non_moogter(self):
        """You cannot approve a request on a moogt that you are not participating in"""
        random_user = create_user_and_login(self, 'random_user', 'test123')
        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_last_created_status_creates_new_bundle(self):
        """
        If the last created object in a moogt is a status then request action should create
        a new bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 2)
        self.assertEqual(
            MoogtActivityBundle.objects.last().activities.count(), 1)
        self.assertEqual(MoogtActivityBundle.objects.last(
        ).activities.first().pk, self.moogt_activity.pk)

    # def test_last_created_argument_creates_new_bundle(self):
    #     """
    #     If the last created object in a moogt is a status then request action should create
    #     a new bundle
    #     """
    #     opposition = create_user_and_login(self, 'opposition', 'pass123')
    #     self.moogt.set_opposition(opposition)
    #     self.moogt.set_proposition(self.user)
    #     self.moogt.save()

    #     moogt_status = MoogtStatus.objects.create(
    #         moogt=self.moogt, status=MoogtStatus.STATUS.paused)
    #     bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
    #     argument = create_argument(
    #         moogt=self.moogt, argument='test argument', user=self.user)

    #     response = self.post(self.moogt_activity.id, {
    #                          'status': ActivityStatus.DECLINED.value})

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(MoogtActivityBundle.objects.count(), 2)
    #     self.assertEqual(
    #         MoogtActivityBundle.objects.last().activities.count(), 1)
    #     self.assertEqual(MoogtActivityBundle.objects.last(
    #     ).activities.first().pk, self.moogt_activity.pk)

    def test_last_created_bundle_updates_last_bundle(self):
        """
        If the last created object in a moogt is a bundle the request action should add the
        activity in the bundle
        """
        opposition = create_user_and_login(self, 'opposition', 'pass123')
        self.moogt.set_opposition(opposition)
        self.moogt.set_proposition(self.user)
        self.moogt.save()

        argument = create_argument(
            moogt=self.moogt, argument='test argument', user=self.user)
        moogt_status = MoogtStatus.objects.create(
            moogt=self.moogt, status=MoogtStatus.STATUS.paused)
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)

        response = self.post(self.moogt_activity.id, {
                             'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(bundle.activities.count(), 1)
        self.assertEqual(bundle.activities.first().pk, self.moogt_activity.pk)


class GetMoogtHighlightsApiViewTests(APITestCase):
    def get(self, moogt_id):
        url = reverse('api:moogts:get_moogt_highlights',
                      kwargs={'version': 'v1', 'pk': moogt_id})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt()

        self.most_applauded: Argument = create_argument(
            moogt=self.moogt, argument='most applauded', user=self.user)
        self.most_applauded.stats.applauds.add(self.user)
        # Create two reaction views.
        reaction_view = View(parent_argument=self.most_applauded,
                             reaction_type=ReactionType.ENDORSE.name,
                             type=ViewType.ARGUMENT_REACTION.name)
        reaction_view.delete()
        reaction_view = View(parent_argument=self.most_applauded,
                             reaction_type=ReactionType.ENDORSE.name,
                             type=ViewType.ARGUMENT_REACTION.name)
        reaction_view.delete()

        self.most_agreed = create_argument(
            moogt=self.moogt, argument='most agreed', user=self.user)
        self.most_agreed.argument_reactions.create(
            reaction_type=ReactionType.ENDORSE.name, user=self.user)

        self.most_disagreed = create_argument(
            moogt=self.moogt, argument='most disagreed', user=self.user)
        self.most_disagreed.argument_reactions.create(
            reaction_type=ReactionType.DISAGREE.name, user=self.user)

        self.most_commented = create_argument(
            moogt=self.moogt, argument='most commented', user=self.user)
        self.most_commented.comment_count = 1
        self.most_commented.save()

    def test_non_authenticated_user(self):
        """
        A non authenticated user is not allowed to get highlights of a moogt, and thus should
        get a not authorized response.
        """
        self.client.logout()
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """Should get a 404 response for a non existing moogt."""
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_most_applauded_argument(self):
        """Should get the most applauded argument."""
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['most_applauded']['id'], self.most_applauded.id)

    def test_most_agreed_argument(self):
        """Should get the most agreed argument."""
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['most_agreed']
                         ['id'], self.most_agreed.id)

    def test_most_disagreed(self):
        """Should get the most disagreed argument."""
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['most_disagreed']['id'], self.most_disagreed.id)

    def test_get_most_commented(self):
        """Should get the most commented argument."""
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['most_commented']['id'], self.most_commented.id)


class MakeMoogtDonationApiViewTests(APITestCase):
    def post(self, moogt_id, body=None):
        url = reverse('api:moogts:make_moogt_donation',
                      kwargs={'version': 'v1', 'pk': moogt_id})
        return self.client.post(url, body, format='json')

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        Wallet.objects.create(user=self.user)
        self.proposition = create_user('proposition', 'pass123')
        Wallet.objects.create(user=self.proposition)
        self.opposition = create_user('opposition', 'pass123')
        Wallet.objects.create(user=self.opposition)
        self.moogt = create_moogt()
        self.moogt.set_opposition(self.opposition)
        self.moogt.set_proposition(self.proposition)
        self.moogt.save()

    def test_non_authenticated_user(self):
        """For non authenticated users return a 401 response."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """Should respond with a not found response for a moogt that doesn't exist."""
        response = self.post(404, None)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_proposition_or_opposition_not_allowed_to_make_donation(self):
        """Should not allow moogters to make a donation."""
        proposition = create_user_and_login(self, 'prop', 'pass123')
        self.moogt.set_proposition(proposition)
        self.moogt.save()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.moogt.set_proposition(None)
        self.moogt.set_opposition(proposition)
        self.moogt.save()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_moderator_to_make_donation(self):
        """Moderators are not allowed to make donations"""
        moderator = create_user_and_login(self, 'moderator', 'pass123')

        self.moogt.set_moderator(moderator)
        self.moogt.save()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_make_a_donation(self):
        """Make a successful donation, should get a 2xx response."""
        response = self.post(self.moogt.id, {'amount': 1,
                                             'donation_for_proposition': True,
                                             'message': 'test message'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.donations.count(), 1)
        donation = Donation.objects.first()
        self.assertEqual(donation.user, self.user)
        self.assertEqual(donation.amount, 1)
        self.assertEqual(donation.donation_for_proposition, True)
        self.assertEqual(donation.message, 'test message')
        self.assertEqual(donation.donated_for, self.proposition)
        self.assertEqual(donation.is_anonymous, False)
        self.assertEqual(response.data['user_id'], self.user.id)

    def test_make_a_donation_without_message(self):
        """Make a successful donation without a message, should get a 2xx response."""
        response = self.post(self.moogt.id, {'amount': 1,
                                             'donation_for_proposition': True})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.assertEqual(self.moogt.donations.count(), 1)
        donation = Donation.objects.first()
        self.assertEqual(donation.user, self.user)
        self.assertEqual(donation.amount, 1)
        self.assertEqual(donation.donation_for_proposition, True)
        self.assertEqual(donation.donated_for, self.proposition)
        self.assertEqual(donation.is_anonymous, False)
        self.assertEqual(response.data['user_id'], self.user.id)

    def test_make_anonymous_donation(self):
        """Make a successful anonymous donation"""
        response = self.post(self.moogt.id, {'amount': 1,
                                             'donation_for_proposition': True,
                                             'message': 'test message',
                                             'is_anonymous': True})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_anonymous'], True)
        self.assertIsNone(response.data['user_id'])
        self.assertIsNone(response.data['user'])

    def test_make_donation_when_you_do_not_have_enough_credit_in_wallet(self):
        """Make a donation with insufficient credit. """
        self.user.wallet.credit = 0
        self.user.wallet.save()
        response = self.post(self.moogt.id, {'amount': 1,
                                             'donation_for_proposition': True,
                                             'message': 'test message'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_without_providing_value_for_donation_for_proposition(self):
        """Should respond with bad request."""
        response = self.post(self.moogt.id, {'amount': 1,
                                             'message': 'test message'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_makes_donation_to_the_respective_user_wallet(self):
        """Make a donation to the respective user."""
        initial_user_amount = self.user.wallet.credit
        initial_proposition_amount = self.user.wallet.credit
        initial_opposition_amount = self.user.wallet.credit

        response = self.post(self.moogt.id, {'amount': 5,
                                             'donation_for_proposition': True,
                                             'message': 'test message'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.moogt.refresh_from_db()
        self.assertEqual(self.user.wallet.credit, initial_user_amount - 5)
        self.assertEqual(self.moogt.get_opposition(
        ).wallet.credit, initial_opposition_amount)

    def test_makes_donation_to_the_opposition(self):
        """Make donation to the proposition user."""
        initial_user_amount = self.user.wallet.credit
        initial_proposition_amount = self.user.wallet.credit
        initial_opposition_amount = self.user.wallet.credit

        response = self.post(self.moogt.id, {'amount': 5,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'test message'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.moogt.refresh_from_db()
        self.assertEqual(self.user.wallet.credit, initial_user_amount - 5)
        self.assertEqual(self.moogt.get_proposition(
        ).wallet.credit, initial_proposition_amount)

    def test_donate_200_tokens(self):
        """Make sure the donations range is working properly"""
        initial_user_amount = self.user.wallet.credit
        initial_proposition_amount = self.user.wallet.credit
        initial_opposition_amount = self.user.wallet.credit

        response = self.post(self.moogt.id, {'amount': 200,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'test message'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.moogt.refresh_from_db()
        self.assertEqual(self.user.wallet.credit, initial_user_amount - 200)
        self.assertEqual(self.moogt.get_proposition(
        ).wallet.credit, initial_proposition_amount)
        self.assertEqual(Donation.objects.first().level,
                         DonationLevel.LEVEL_4.name)

    def test_donate_1500_tokens(self):
        """Make sure the donations range is working properly"""
        initial_user_amount = self.user.wallet.credit
        initial_proposition_amount = self.user.wallet.credit
        initial_opposition_amount = self.user.wallet.credit

        response = self.post(self.moogt.id, {'amount': 1500,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'test message'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.moogt.refresh_from_db()
        self.assertEqual(self.user.wallet.credit, initial_user_amount - 1500)
        self.assertEqual(self.moogt.get_proposition(
        ).wallet.credit, initial_proposition_amount)
        self.assertEqual(Donation.objects.first().level,
                         DonationLevel.LEVEL_5.name)
        self.assertEqual(Donation.objects.first().amount, 1500)

    def test_valid_char_limit(self):
        """Test donations on valid character limits for every donation levels"""
        response = self.post(self.moogt.id, {'amount': 1,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 50})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.post(self.moogt.id, {'amount': 5,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 75})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.post(self.moogt.id, {'amount': 10,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 100})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.post(self.moogt.id, {'amount': 100,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 150})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.post(self.moogt.id, {'amount': 1000,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 200})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_char_limit(self):
        """Test donations on invalid character limits for every donation levels"""
        response = self.post(self.moogt.id, {'amount': 1,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 51})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.post(self.moogt.id, {'amount': 5,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 76})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.post(self.moogt.id, {'amount': 10,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 101})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.post(self.moogt.id, {'amount': 100,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 151})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.post(self.moogt.id, {'amount': 1000,
                                             'donation_for_proposition': False,
                                             'donation_for': self.opposition.id,
                                             'message': 'a' * 201})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GetBundleActivitiesApiViewTests(APITestCase):
    def get(self, bundle_id):
        url = reverse('api:moogts:bundle_activities', kwargs={
                      'version': 'v1', 'pk': bundle_id})
        return self.client.get(url)

    def setUp(self) -> None:
        self.proposition = create_user("username", "password")
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.proposition,
                                            opposition=self.user,
                                            resolution="test moogt",
                                            started_at_days_ago=1,
                                            has_opening_argument=True)

    def test_success(self):
        """
        Get list of activities from a bundle
        """
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        moogt_activity = MoogtActivity.objects.create(moogt=self.moogt, bundle=bundle,
                                                      type=MoogtActivityType.CARD_REQUEST.value)

        response = self.get(bundle.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], moogt_activity.pk)

    def test_non_authenticated_user(self):
        """
        Non-authenticated user should get a non-authorized response.
        """
        self.client.logout()
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        response = self.get(bundle.pk)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_with_non_existing_bundle(self):
        """
        Should respond with a 404 response if the moogt doesn't exist
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_ordering_of_activities_in_a_bundle(self):
        """
        Get list of activities from a bundle
        """
        bundle = MoogtActivityBundle.objects.create(moogt=self.moogt)
        moogt_activity1 = MoogtActivity.objects.create(moogt=self.moogt, bundle=bundle,
                                                       type=MoogtActivityType.CARD_REQUEST.value)

        moogt_activity2 = MoogtActivity.objects.create(moogt=self.moogt, bundle=bundle,
                                                       type=MoogtActivityType.CARD_REQUEST.value)

        response = self.get(bundle.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], moogt_activity2.pk)
        self.assertEqual(response.data['results'][1]['id'], moogt_activity1.pk)


class ListDonationsApiViewTests(APITestCase):
    def get(self, moogt_id, for_proposition=True):
        url = reverse('api:moogts:list_moogt_donations',
                      kwargs={'version': 'v1', 'pk': moogt_id})
        if not for_proposition:
            url = url + '?donation_for_proposition=false'
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt()
        self.donation = Donation.objects.create(user=self.user,
                                                moogt=self.moogt,
                                                amount=5,
                                                donation_for_proposition=True)
        self.donation2 = Donation.objects.create(user=self.user,
                                                 moogt=self.moogt,
                                                 amount=5,
                                                 donation_for_proposition=False)

    def test_non_existing_moogt(self):
        """Test non existing moogt. Should respond with a 404 response."""
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_donations_for_a_moogt(self):
        """Get the list of donations for a moogt."""
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.donation.id)
        self.assertEqual(response.data['results']
                         [0]['moogt_id'], self.moogt.id)

    def test_donation_for_opposition(self):
        """Get the donations for the opposition."""
        response = self.get(self.moogt.id, False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.donation2.id)

    def test_ordering_of_donations(self):
        """Latest donations should appear first """
        donation3 = Donation.objects.create(user=self.user,
                                            moogt=self.moogt,
                                            amount=10,
                                            donation_for_proposition=False)
        response = self.get(self.moogt.id, False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], donation3.id)
        self.assertEqual(response.data['results'][1]['id'], self.donation2.id)

    def test_highest_opposition_donation(self):
        """Highest opposition donations are included in the response"""
        donation3 = Donation.objects.create(user=self.user,
                                            moogt=self.moogt,
                                            amount=10,
                                            donation_for_proposition=False)
        response = self.get(self.moogt.id, False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['highest']['id'], donation3.pk)

    def test_highest_proposition_donation(self):
        """Highest proposition donations are included in the response"""
        donation3 = Donation.objects.create(user=self.user,
                                            moogt=self.moogt,
                                            amount=10,
                                            donation_for_proposition=True)
        response = self.get(self.moogt.id, True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['highest']['id'], donation3.pk)

    def test_highest_proposition_with_no_donation(self):
        """Getting Highest proposition for empty donations list should not cause a problem"""
        Donation.objects.all().delete()
        response = self.get(self.moogt.id, False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class QuitMoogtApiViewTests(APITestCase):
    def get(self, moogt_id):
        url = reverse('api:moogts:quit_moogt', kwargs={
                      'version': 'v1', 'pk': moogt_id})
        return self.client.get(url)

    def setUp(self) -> None:
        self.proposition = create_user("username345678", "password")
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.proposition,
                                            opposition=self.user,
                                            resolution="test moogt",
                                            started_at_days_ago=1,
                                            has_opening_argument=True)

        self.follower = create_user('follower', 'password')
        self.moogt.followers.add(self.follower)
        self.argument = create_argument(
            argument='test argument', user=self.user)

    def test_successfully_quit_moogt(self):
        """
        test successfully quit moogt
        """
        response = self.get(self.moogt.id)
        self.moogt.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.moogt.quit_by, self.user)
        # because self.user is the opposition the moogts next_turn_proposition should be True
        # to input last argument
        self.assertEqual(self.moogt.next_turn_proposition, True)
        self.assertEqual(self.moogt.arguments.count(), 1)
        self.assertEqual(self.moogt.statuses.count(), 1)
        self.assertEqual(self.moogt.statuses.first().status,
                         MoogtStatus.STATUS.broke_off)

    def test_successfully_quit_by_moderator(self):
        """tests if the moderator successfully quits the moogt"""

        # moderator = create_user_and_login(self)
        user = create_user('username12', 'pass123')
        moogt = create_moogt_with_user(self.proposition,
                                       opposition=user,
                                       resolution="test moogt",
                                       started_at_days_ago=1,
                                       has_opening_argument=True)
        moogt.set_moderator(self.user)

        moogt.save()

        response = self.get(moogt.id)

        moogt.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(moogt.statuses.count(), 0)
        self.assertEqual(moogt.moderator, None)
        self.moogt.next_turn_proposition = False

    def test_non_participant_quitting_moogt(self):
        """
        If a user that is not participating on a moogt is trying to quit
        response should fail
        """
        self.user = create_user_and_login(self, username="test_username")
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quitting_moogt_without_turn(self):
        """
        If a user that is participating on a moogt but is not their turn
        response should fail
        """
        argument = create_argument(
            self.user, "test argument", moogt=self.moogt)
        response = self.get(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_check_notification_sent(self):
        """
        If a moogter quits a moogt the opponent of the quitter and the followers
        of the moogt get notifications of quitting.
        """
        response = self.get(self.moogt.id)

        # the propositions notifications
        opp_not = self.proposition.notifications.filter(verb='quit').first()
        # the followers notifications
        foll_not = self.follower.notifications.filter(verb='quit').first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.proposition.notifications.filter(
            verb='quit').count(), 1)
        self.assertEqual(opp_not.actor, self.user)
        self.assertEqual(opp_not.target, self.moogt)

        self.assertEqual(self.follower.notifications.filter(
            verb='quit').count(), 1)
        self.assertEqual(foll_not.actor, self.user)
        self.assertEqual(foll_not.target, self.moogt)

    def test_if_the_moogt_has_a_bundle(self):
        """"validating that the moogt has a bundle when quitting."""

        response = self.get(self.moogt.id)
        self.moogt.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.moogt.bundles.count(), 1)
        self.assertEqual(self.moogt.bundles.first().activities.count(), 1)
        self.assertEqual(self.moogt.bundles.first(
        ).activities.first().type, MoogtActivityType.QUIT.value)
        self.assertEqual(
            self.moogt.bundles.first().activities.first().user, self.user)


class GetUsersFollowingMoogtApiViewTests(APITestCase):
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.proposition = create_user('test_username', 'test_password')
        self.moogt = create_moogt_with_user(self.proposition,
                                            opposition=self.user,
                                            resolution="test moogt",
                                            started_at_days_ago=1)

    def get(self, pk):
        url = reverse('api:moogts:users_following',
                      kwargs={'version': 'v1', 'pk': pk})
        return self.client.get(url)

    def test_successfully_list_followers_of_moogt(self):
        """If a moogt has followers response should include them"""
        user = create_user('test_username2', 'test_password')
        self.moogt.followers.add(user)
        response = self.get(self.moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_moogt_that_does_not_exist(self):
        """
        You should get a not found response for a moogt that doesn't exist.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_result_is_sorted_based_on_followers_count(self):
        """
        The list of users that is going to be returned should be sorted based on followers count.
        """
        user_1 = create_user('user_1', 'test_password')
        user_2 = create_user('user_2', 'test_password')

        follower = create_user('follower', 'test_password')
        user_2.follower.add(follower)

        self.moogt.followers.add(user_1)
        self.moogt.followers.add(user_2)

        response = self.get(self.moogt.id)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], user_2.id)


class MoogtReportApiViewTests(APITestCase):
    def post(self, moogt_id, data=None):
        url = reverse('api:moogts:report_moogt', kwargs={
                      'version': 'v1', 'pk': moogt_id})
        return self.client.post(url, data)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = MoogtFactory.create()

    def test_non_logged_in_user(self):
        """Should respond with a not-authorized response for a non-logged in user."""
        self.client.logout()
        response = self.post(self.moogt.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_moogt(self):
        """Should respond with a not-found response for a moogt that does not exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('api.mixins.ReportMixin.validate')
    def test_should_call_validate(self, mock_validate: MagicMock):
        self.post(self.moogt.id)
        mock_validate.assert_called()
        self.assertEqual(mock_validate.call_count, 3)

    @patch('api.mixins.ReportMixin.notify_admins')
    def test_notify_admins(self, mock_validate: MagicMock):
        """Should notify admins."""
        self.post(self.moogt.id, {
                  'link': 'https://moogter.link', 'reason': 'test reason'})
        mock_validate.assert_called_once()

    def test_should_create_a_moogt_report(self):
        """Should create a report for a moogt if it passes validation"""
        response = self.post(
            self.moogt.id, {'link': 'https://moogter.link', 'reason': 'test reason'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        moogt_reports = MoogtReport.objects.all()
        self.assertEqual(moogt_reports.count(), 1)
        self.assertEqual(moogt_reports.first().reported_by, self.user)
        self.assertEqual(moogt_reports.first().moogt, self.moogt)
