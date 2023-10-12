# Create your tests here.
import datetime
import json
import os
from unittest.mock import MagicMock, patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from api.enums import ReactionType, ViewType
from api.tests.tests import create_user_and_login
from api.tests.utility import create_user_and_login, create_argument, create_comment, create_moogt_with_user, \
    create_argument_activity, generate_photo_file, create_view, create_user
from arguments.models import Argument, ArgumentReport, ArgumentStats, ArgumentActivity, ArgumentActivityType, ArgumentReactionType, \
    ArgumentImage
from arguments.tests.factories import ArgumentFactory
from meda.enums import ArgumentType, ActivityStatus
from meda.tests.test_models import create_moogt
from meda.models import AbstractActivityAction
from moogtmeda.settings import MEDIA_ROOT
from moogts.models import Moogt, ReadBy, MoogtActivity, MoogtStatus, MoogtActivityType, MoogtActivityBundle
from moogts.serializers import MoogtNotificationSerializer
from notifications.enums import NOTIFICATION_TYPES
from users.models import Activity, MoogtMedaUser, CreditPoint, ActivityType
from views.models import View


class ApplaudArgumentApiViewTests(APITestCase):
    def post(self, argument_id):
        url = reverse('api:arguments:applaud_argument', kwargs={
                      'version': 'v1', 'pk': argument_id})
        return self.client.post(url)

    def test_applaud_a_argument(self):
        """
        test applaud to a argument successfully
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument")
        response = self.post(argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.stats.applauds.count(), 1)

    def test_unsend_notification_when_applaud_is_toggled(self):
        """
        If a user takes back their applaud then the notification must be unsent
        for the creator
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        argument = create_argument(creator, "test argument")
        response = self.post(argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(creator.notifications.filter(
            type=NOTIFICATION_TYPES.argument_applaud).count(), 1)

        response = self.post(argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(creator.notifications.filter(
            type=NOTIFICATION_TYPES.argument_applaud).count(), 0)

    def test_applaud_argument_from_a_non_creator(self):
        """
        If a user is a non reactor and reacts on an argument
        the creator of the argument should get a notification of the applaud
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        argument = create_argument(creator, "test argument")
        response = self.post(argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.stats.applauds.count(), 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type,
                         NOTIFICATION_TYPES.argument_applaud)

    def test_applaud_a_non_existing_argument(self):
        """
        test applaud to a non existing argument
        """
        user = create_user_and_login(self)
        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ArgumentStats.objects.count(), 0)

    def test_applaud_and_try_to_applaud_again(self):
        """
        If there is an applaud to an argument and a user tries to applaud again, the applaud should
        be toggled. That is the registered applaud should be removed.
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument")
        # Applaud
        self.post(argument.id)
        # Applaud again
        response = self.post(argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.stats.applauds.count(), 0)
        self.assertEqual(ArgumentStats.objects.first().applauds.count(), 0)

    def test_stats_are_properly_set(self):
        """
        The applauds count field should be set properly for an argument.
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument")
        # Applaud
        response = self.post(argument.id)

        self.assertEqual(response.data['stats']['applaud']['count'], 1)
        response = self.post(argument.id)
        self.assertEqual(response.data['stats']['applaud']['count'], 0)

    def tests_stats_has_applauded_should_be_properly_set(self):
        """
        The has_applauded field should be properly set.
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument")
        # Applaud
        response = self.post(argument.id)
        self.assertTrue(response.data['stats']['applaud']['selected'])
        response = self.post(argument.id)
        self.assertFalse(response.data['stats']['applaud']['selected'])


class GetArgumentReactingUsersApiViewTests(APITestCase):
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(self.user, opposition=True, resolution="test moogt resolution",
                                            started_at_days_ago=1)
        self.argument = create_argument(
            self.user, 'test view', moogt=self.moogt)

    def get(self, pk, reaction_type=None):
        url = reverse('api:arguments:users_reacting',
                      kwargs={'version': 'v1', 'pk': pk})
        if reaction_type:
            url += f'?type={reaction_type}'
        return self.client.get(url)

    def test_argument_that_does_not_exist(self):
        """
        You should get a not found response for a argument that doesn't exist.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_users_who_applauded_the_argument(self):
        """
        You should get the users who applauded the argument, if it has applaud reactions.
        """
        user = create_user('reaction_user', 'test_password')
        self.argument.stats.applauds.add(user)
        response = self.get(self.argument.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_get_users_who_endorsed_the_argument(self):
        """
        You should get the users who endorsed the argument, if it has endorse reactions.
        """
        user = create_user('reaction_user', 'test_password')
        reaction_view = create_view(user, 'test reaction')
        reaction_view.parent_argument = self.argument
        reaction_view.type = ViewType.ARGUMENT_REACTION.name
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get(
            self.argument.id, reaction_type=ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_get_moogters_who_reacted_on_the_argument(self):
        """
        You should get the moogter the who endorsed the argument.
        """
        rxn_argument = Argument.objects.create(user=self.user,
                                               react_to=self.argument,
                                               moogt=self.moogt,
                                               reaction_type=ArgumentReactionType.ENDORSEMENT.name)

        response = self.get(
            self.argument.id, reaction_type=ReactionType.ENDORSE.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], self.user.id)

    def test_get_users_who_disagreed_the_view(self):
        """
        You should get the users who disagreed with the view, if it has disagree reactions.
        """
        user = create_user('reaction_user', 'test_password')
        reaction_view = create_view(user, 'test reaction')
        reaction_view.parent_argument = self.argument
        reaction_view.type = ViewType.ARGUMENT_REACTION.name
        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.save()

        response = self.get(
            self.argument.id, reaction_type=ReactionType.DISAGREE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_invalid_type_query_parameter(self):
        """
        If the type query param is invalid, it should respond with a bad request response.
        """
        response = self.get(self.argument.id, reaction_type='invalid')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_is_sorted_based_on_followers_count(self):
        """
        The list of users that is going to be returned should be sorted based on followers count.
        """
        user_1 = create_user('user_1', 'test_password')
        user_2 = create_user('user_2', 'test_password')

        follower = create_user('follower', 'test_password')
        user_2.follower.add(follower)

        self.argument.stats.applauds.add(user_1)
        self.argument.stats.applauds.add(user_2)

        response = self.get(self.argument.id)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], user_2.id)

    def test_users_who_you_are_following_should_be_ranked_first(self):
        """
        The people that you're following should be ranked highest in the response.
        """
        user_1 = create_user('user_1', 'test_password')
        follower_user = create_user('follower_user', 'test_password')
        user_1.follower.add(follower_user)
        user_2 = create_user('user_2', 'test_password')
        user_2.follower.add(self.user)

        self.argument.stats.applauds.add(user_1)
        self.argument.stats.applauds.add(user_2)

        response = self.get(self.argument.id)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], user_2.id)


class CreateArgumentViewTests(APITestCase):
    def post(self, data):
        url = reverse('api:arguments:create_argument',
                      kwargs={'version': 'v1'})
        return self.client.post(url, data, format='json')

    def test_non_existing_moogt(self):
        """
        If the moogt doesn't exist, it should return a 404 response code
        """
        create_user_and_login(self)
        response = self.post({'moogt_id': 404})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_not_authenticated(self):
        """
        If the user is not authenticated, it should not respond with not authorized status code
        """
        response = self.post({'moogt_id': 404})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_request_is_not_valid(self):
        """
        If the request is not valid, it should not create an argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution')
        moogt.set_proposition(user)
        moogt.save()

        response = self.post({'moogt_id': moogt.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_where_current_user_is_not_either_proposition_or_opposition(self):
        """
        If the current user is not either the proposition or opposition of the moogt,
        it should not create the argument
        """
        moogt = create_moogt(resolution='test resolution')
        create_user_and_login(self)
        response = self.post({'moogt_id': moogt.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_is_proposition(self):
        """
        If the user is the proposition for the moogt and next_turn_proposition is True,
        it should create an argument
        """
        user = create_user_and_login(self)

        moogt = create_moogt(opposition=True, started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['argument'], 'test argument')

        moogt = Moogt.objects.get(pk=moogt.id)
        self.assertFalse(moogt.get_next_turn_proposition())
        self.assertTrue(moogt.get_last_posted_by_proposition())
        latest_argument_added_at = moogt.get_latest_argument_added_at().replace(second=0,
                                                                                microsecond=0)
        self.assertEqual(latest_argument_added_at,
                         timezone.now().replace(second=0, microsecond=0))
        self.assertEqual(moogt.arguments.count(), 1)
        self.assertEqual(moogt.arguments.first().type,
                         ArgumentType.NORMAL.name)

    def test_with_expired_card_request(self):
        """Card requests should expire after a turn expires."""
        user = create_user_and_login(self)

        moogt: Moogt = create_moogt(opposition=True, started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.save()

        moogt.activities.create(type=MoogtActivityType.CARD_REQUEST.name)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['argument'], 'test argument')

        moogt.refresh_from_db()
        self.assertEqual(moogt.activities.count(), 0)

    def test_create_argument_after_a_forfeited_turn(self):
        """
        If there is a forfeited turn, then the next in turn user should be able to create an argument.
        """
        user = create_user_and_login(self)

        now = timezone.now()
        moogt = create_moogt(
            opposition=user, reply_time=timezone.timedelta(minutes=3))
        moogt.set_opposition(user)
        moogt.set_started_at(now - datetime.timedelta(minutes=4))
        moogt.set_latest_argument_added_at(now - datetime.timedelta(minutes=4))
        moogt.set_next_turn_proposition(False)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['argument'], 'test argument')

    def test_authenticated_user_is_proposition_and_next_turn_proposition_is_false(self):
        """
        If the user is the proposition for the moogt and next_turn_proposition is False,
        it should not create an argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             opposition=True, started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.set_next_turn_proposition(False)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        moogt = Moogt.objects.get(id=moogt.id)
        self.assertEqual(moogt.arguments.count(), 0)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_authenticated_user_is_opposition(self):
        """
        If the user is the opposition for the moogt and next_turn_proposition is False,
        it should create an argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt(started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_next_turn_proposition(False)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['argument'], 'test argument')
        moogt = Moogt.objects.get(id=moogt.id)
        self.assertTrue(moogt.get_next_turn_proposition())
        self.assertFalse(moogt.get_last_posted_by_proposition())
        latest_argument_added_at = moogt.get_latest_argument_added_at().replace(second=0,
                                                                                microsecond=0)
        self.assertEqual(latest_argument_added_at,
                         timezone.now().replace(second=0, microsecond=0))
        self.assertEqual(moogt.arguments.count(), 1)
        self.assertEqual(moogt.arguments.first().type,
                         ArgumentType.NORMAL.name)

    def test_authenticated_user_is_opposition_and_next_turn_proposition_is_true(self):
        """
        If the user is the opposition for the moogt and next_turn_proposition is True,
        it should not create an argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_next_turn_proposition(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_a_valid_request_activity_must_be_recorded(self):
        """
        If the request is valid, the activity must be recorded properly
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.set_opposition(create_user('opposition_user', 'testpassword'))
        moogt.set_next_turn_proposition(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        argument_id = response.data['id']
        activity = Activity.objects.get(object_id=argument_id)
        self.assertIsNotNone(activity)
        self.assertEqual(activity.profile, user.profile)

    def test_notifications_sent(self):
        """
        If the request is valid, notification must be sent to the appropriate recipient
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_proposition(user)
        opposition_user = create_user('opposition_user', 'testpassword')
        moogt.set_opposition(opposition_user)
        moogt.set_next_turn_proposition(True)
        moogt.save()

        self.post({'moogt_id': moogt.id,
                   'argument': 'test argument',
                   'status': 'continue'})

        recipient = MoogtMedaUser.objects.get(pk=opposition_user.id)
        user = MoogtMedaUser.objects.get(pk=user.id)
        self.assertEqual(recipient.notifications.count(), 1)
        self.assertEqual(user.notifications.count(), 0)
        self.assertIsNotNone(recipient.notifications.first().data)
        self.assertEqual(recipient.notifications.first(
        ).data['data']['moogt'], MoogtNotificationSerializer(moogt).data)

    def test_create_concluding_argument(self):
        """
        If the type of the argument to be created is concluding, it should be created.
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_has_ended(True)
        # While the logged in user is a moogt opposition and next_turn is proposition
        # it should still let the opposition input the concluding argument despite
        # next_turn_proposition being true
        moogt.set_next_turn_proposition(True)

        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.CONCLUDING.name})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        argument_exists = Argument.objects.filter(
            type=ArgumentType.CONCLUDING.name).exists()
        self.assertTrue(argument_exists)

    def test_create_two_concluding_argument(self):
        """
        If the type of the argument to be created twice by the same user it should only
        allow one to be created
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_has_ended(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.CONCLUDING.name})

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.CONCLUDING.name})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Argument.objects.count(), 1)

    def test_reply_to_argument(self):
        """
        test creating an argument as a reply to another argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(
            user, opposition=True, resolution="test moogt resolution", started_at_days_ago=1)
        argument = Argument(moogt=moogt, user=user, argument="test argument")
        argument.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test reply argument',
                              'reply_to': argument.id,
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_argument_for_a_moogt_that_has_not_ended(self):
        """
        If a moogt has not ended, you cannot create a concluding argument.
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.CONCLUDING.name})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_participant_who_quited_tries_to_write_concluding_argument(self):
        """
        A participant who has quitted a proposition, cannot write the concluding argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.quit_by = user
        moogt.set_has_ended(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.CONCLUDING.name})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_participant_who_quited_tries_to_write_normal_argument(self):
        """
        A participant who has quitted a moogt should not write an argument
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.quit_by = user
        moogt.set_has_ended(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.NORMAL.name})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_participant_on_a_quited_moogt_tries_to_write_normal_argument_more_than_once(self):
        """
        A participant who is in a quited moogt but hasn't ended should only be allowed one more argument
        and then moogt has to end and can not create any more normal arguments
        """
        user = create_user_and_login(self)
        user_1 = create_user("username", "password")
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.set_opposition(user_1)
        moogt.quit_by = user_1
        moogt.set_has_ended(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.NORMAL.name})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.NORMAL.name})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_participant_cannot_write_concluding_argument_while_it_is_their_turn(self):
        """
        In order for a participant to write a concluding argument they must have a go
        at their turn first.
        """
        user = create_user_and_login(self)
        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_next_turn_proposition(False)
        moogt.set_has_ended(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'type': ArgumentType.CONCLUDING.name})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(moogt.arguments.count(), 1)

    def test_proposition_created_field_true(self):
        """
        If a proposition created an argument then proposition_created must be true
        """
        opposition = create_user_and_login(self)
        proposition = create_user("username", "password")
        moogt = create_moogt_with_user(proposition_user=proposition, opposition=opposition,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        create_argument(proposition, "argument", moogt=moogt)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['proposition_created'], False)

    def test_opposition_created_field_false(self):
        """
        If a opposition created and argument then proposition_created must be false
        """
        proposition = create_user_and_login(self)
        opposition = create_user("username", "password")

        moogt = create_moogt_with_user(proposition_user=proposition, opposition=opposition,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['proposition_created'], True)

    def test_reaction_argument(self):
        """
        If a reaction to an argument is supplied by moogters it should create an
        argument based on the reaction
        """
        opposition = create_user_and_login(self)
        proposition = create_user("username", "password")

        moogt = create_moogt_with_user(proposition_user=proposition, opposition=opposition,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(proposition, "argument", moogt=moogt)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'react_to': argument.id,
                              'reaction_type': ArgumentReactionType.ENDORSEMENT.name,
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['react_to']['id'], argument.id)
        self.assertEqual(
            response.data['reaction_type'], ArgumentReactionType.ENDORSEMENT.name)

    def test_reaction_argument_without_type(self):
        """
        If a reaction to an argument is supplied by moogters without reaction type
        request should fail
        """
        opposition = create_user_and_login(self)
        proposition = create_user("username", "password")

        moogt = create_moogt_with_user(proposition_user=proposition, opposition=opposition,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(proposition, "argument", moogt=moogt)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'react_to': argument.id,
                              'status': 'continue'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_with_uploaded_image(self):
        """If there are uploaded images the argument should be created along those images."""
        argument_image = ArgumentImage.objects.create()

        user = create_user_and_login(self)
        moogt = create_moogt(started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_next_turn_proposition(False)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue',
                              'images': [argument_image.id]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        argument = Argument.objects.get(pk=response.data['id'])
        self.assertEqual(argument.images.count(), 1)

    def test_create_with_more_than_four_images(self):
        """Maximum image upload number is four."""
        argument_image = ArgumentImage.objects.create()
        argument_image2 = ArgumentImage.objects.create()
        argument_image3 = ArgumentImage.objects.create()
        argument_image4 = ArgumentImage.objects.create()
        argument_image5 = ArgumentImage.objects.create()

        user = create_user_and_login(self)
        moogt = create_moogt(started_at_days_ago=1)
        moogt.set_opposition(user)
        moogt.set_next_turn_proposition(False)
        moogt.save()

        images = [argument_image.id,
                  argument_image2.id,
                  argument_image3.id,
                  argument_image4.id,
                  argument_image5.id]
        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue',
                              'images': images})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_argument_with_paused_moogt(self):
        """Should not allow to create argument for a moogt that is paused."""
        user = create_user_and_login(self)
        moogt = create_moogt(started_at_days_ago=1)
        moogt.set_proposition(user)
        moogt.set_is_paused(True)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_last_argument_created_by_proposition_then_duration_ends(self):
        """
        If the last argument created is by proposition and the duration ends
        it should let the opposition create the last argument and create
        Moogt Over status
        """
        proposition = create_user("username", "password")
        opposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=opposition, started_at_days_ago=3)

        argument_prop = create_argument(proposition, "test argument", moogt)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument 2',
                              'status': 'continue'})

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MoogtStatus.objects.count(), 1)
        self.assertEqual(MoogtStatus.objects.first().status,
                         MoogtStatus.STATUS.duration_over)
        self.assertEqual(moogt.get_has_ended(), False)

    #     last argument created by opposition and then duration ended
    def test_last_argument_created_by_opposition_then_duration_ends(self):
        """
        If the last argument created is by opposition and the duration ends
        it should let the proposition go one more round and
        not end the moogt and also should not create Moogt Over Status
        """
        opposition = create_user("username", "password")
        proposition = create_user_and_login(self)

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=opposition, started_at_days_ago=3)

        argument_prop = create_argument(proposition, 'test argument', moogt)
        argument_opp = create_argument(opposition, "test argument", moogt)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MoogtStatus.objects.count(), 1)
        self.assertEqual(moogt.get_has_ended(), False)

        self.client.force_login(opposition)

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        moogt.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MoogtStatus.objects.count(), 1)
        self.assertEqual(moogt.get_has_ended(), True)

    def test_create_argument_for_moderator(self):
        """Tests if the moderator can create an argument without a turn"""

        opposition = create_user("opposition", "password")
        proposition = create_user("proposition", "password")

        user = create_user_and_login(self)

        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)
        moogt.set_opposition(opposition)
        moogt.set_proposition(proposition)
        moogt.set_moderator(user)

        moogt.save()

        prev_value = moogt.get_next_turn_proposition()
        prev_arg_added_at = moogt.get_latest_argument_added_at()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        moogt.refresh_from_db()
        next_val = moogt.get_next_turn_proposition()
        next_arg_added_at = moogt.get_latest_argument_added_at()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'],
                         ArgumentType.MODERATOR_ARGUMENT.name)

        self.assertEqual(prev_value, next_val)
        self.assertEqual(prev_arg_added_at, next_arg_added_at)

    def test_create_argument_for_moderator_multiple_times(self):
        """Tests if the moderator creates an argument multiple times"""

        opposition = create_user("opposition", "password")
        proposition = create_user("proposition", "password")

        user = create_user_and_login(self)

        moogt = create_moogt(resolution='test resolution',
                             started_at_days_ago=1)

        moogt.set_opposition(opposition)
        moogt.set_proposition(proposition)
        moogt.set_moderator(user)
        moogt.save()

        response = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument',
                              'status': 'continue'})

        response2 = self.post({'moogt_id': moogt.id,
                              'argument': 'test argument 2',
                               'status': 'continue'})
        arguments = Argument.objects.all()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(arguments.count(), 2)
        self.assertEqual(arguments.first().get_type(),
                         ArgumentType.MODERATOR_ARGUMENT.name)
        self.assertEqual(arguments.last().get_type(),
                         ArgumentType.MODERATOR_ARGUMENT.name)


class UpvoteDownvoteArgumentViewTests(APITestCase):
    def post(self, argument_id, data):
        url = reverse('api:arguments:upvote_downvote', kwargs={
                      'pk': argument_id, 'version': 'v1'})
        return self.client.post(url, data)

    def test_unauthenticated_user_attempting_to_upvote_or_downvote(self):
        response = self.post(1, {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_argument(self):
        """
        If the argument does, not exist, it should respond with 404 response code
        """
        create_user_and_login(self)
        response = self.post(404, {})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_in_moogt(self):
        """
        If user is either proposition or opposition, they cannot upvote or downvote
        """
        user = create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)
        moogt.set_proposition(user)
        moogt.save()

        response = self.post(moogt.arguments.first().id, {'action': 'upvote'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        moogt.set_proposition(None)
        moogt.set_opposition(user)
        moogt.save()

        response = self.post(moogt.arguments.first().id, {'action': 'upvote'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def assert_vote(self, action):
        user = create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)
        argument = moogt.arguments.first()
        response = self.post(argument.id, {'action': action})

        self.assertEqual(response.status_code, 200)
        argument = Argument.objects.get(pk=argument.id)

        if action == 'upvote':
            self.assertEqual(argument.stats.upvotes.count(), 1)
            self.assertEqual(argument.stats.upvotes.first(), user)
            self.assertEqual(argument.stats.downvotes.count(), 0)
        elif action == 'downvote':
            self.assertEqual(argument.stats.upvotes.count(), 0)
            self.assertEqual(argument.stats.downvotes.count(), 1)
            self.assertEqual(argument.stats.downvotes.first(), user)

    def test_upvote(self):
        """
        If the action is upvote, it should upvote the argument stats
        """
        self.assert_vote('upvote')

    def test_downvote(self):
        """
        If the action is downvote, it should downvote the argument stats
        """
        self.assert_vote('downvote')

    def test_invalid_action(self):
        """
        If the request contains an invalid action, it should not upvote or downvote
        """
        create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)

        argument = moogt.arguments.first()
        response = self.post(argument.id, {'action': 'invalid action'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upvote_credit_point_created(self):
        """
        Upvote activity creates credit points in the database when called from API
        """
        user = create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)

        argument = moogt.arguments.first()
        response = self.post(argument.id, {'action': 'upvote'})

        credit = CreditPoint.objects
        credit_point = credit.first()
        credit_point_count = credit.count()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(credit_point.profile, argument.user.profile)
        self.assertEqual(credit_point_count, 1)
        self.assertEqual(credit_point.type, ActivityType.upvote_argument.name)

    def test_downvote_credit_point_created(self):
        """
        Downvote activity creates credit points in the database when called from API
        """
        user = create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)

        argument = moogt.arguments.first()
        response = self.post(argument.id, {'action': 'downvote'})

        credit = CreditPoint.objects
        credit_point = CreditPoint.objects.first()
        credit_point_count = credit.count()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(credit_point.profile, argument.user.profile)
        self.assertEqual(credit_point_count, 1)
        self.assertEqual(credit_point.type,
                         ActivityType.downvote_argument.name)

    def test_upvote_downvote_upvote_single_credit_point_created(self):
        """
        Upvote activity creates credit points once when upvoted downvoted and upvoted again in the database when called from API
        """
        user = create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)

        argument = moogt.arguments.first()
        response = self.post(argument.id, {'action': 'upvote'})
        response = self.post(argument.id, {'action': 'downvote'})
        response = self.post(argument.id, {'action': 'upvote'})

        credit = CreditPoint.objects
        credit_point = credit.first()
        credit_point_count = credit.count()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(credit_point.profile, argument.user.profile)
        self.assertEqual(credit_point_count, 1)
        self.assertEqual(credit_point.type, ActivityType.upvote_argument.name)

    def test_downvote_upvote_downvote_single_credit_point_created(self):
        """
        Upvote activity creates credit points once when upvoted downvoted and upvoted again in the database when called from API
        """
        user = create_user_and_login(self)
        moogt = create_moogt(has_opening_argument=True)

        argument = moogt.arguments.first()
        response = self.post(argument.id, {'action': 'downvote'})
        response = self.post(argument.id, {'action': 'uovote'})
        response = self.post(argument.id, {'action': 'downvote'})

        credit = CreditPoint.objects
        credit_point = credit.first()
        credit_point_count = credit.count()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(credit_point.profile, argument.user.profile)
        self.assertEqual(credit_point_count, 1)
        self.assertEqual(credit_point.type,
                         ActivityType.downvote_argument.name)


class ArgumentReactionAPIViewTests(APITestCase):
    def post(self, body=None, version='v1'):
        url = reverse('api:arguments:react_argument',
                      kwargs={'version': version})
        return self.client.post(url, body, format='json')

    def test_react_argument(self):
        """
        Make a successful reaction to a argument
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test content'
        ).count(), 1)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)
        self.assertEqual(response.data['stats']['endorse']['selected'], True)
        self.assertEqual(argument.argument_reactions.count(), 1)
        self.assertEqual(proposition.notifications.count(), 1)
        self.assertEqual(proposition.notifications.first().type,
                         NOTIFICATION_TYPES.argument_agree)

    def test_react_has_no_type(self):
        """
        Reaction object request has no type
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")
        response = self.post({'content': 'test content',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endorse_without_a_statement(self):
        """
        It should create a reaction view, if you're trying to agree with an argument
        without a statement.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content__isnull=True,
            user=user
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 1)
        self.assertEqual(proposition.notifications.count(), 1)
        self.assertEqual(proposition.notifications.first().type,
                         NOTIFICATION_TYPES.argument_agree)

    def test_disagree_without_a_statement(self):
        """
        If should create a reaction view, if you're trying to disagree with an argument
        without a statement.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content__isnull=True,
            user=user
        ).count(), 1)
        self.assertEqual(response.data['stats']['disagree']['count'], 1)
        self.assertEqual(response.data['stats']['disagree']['selected'], True)
        self.assertEqual(argument.argument_reactions.count(), 1)
        self.assertEqual(proposition.notifications.count(), 1)
        self.assertEqual(proposition.notifications.first().type,
                         NOTIFICATION_TYPES.argument_disagree)

    def test_react_has_no_argument_id(self):
        """
        test Reaction object request has no argument id
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_react_to_non_existing_argument(self):
        """
        test Reaction object reacts to a non existing argument
        """
        user = create_user_and_login(self)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'argument_id': 1})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_react_to_argument(self):
        """
        test unauthenticated user reacts to a argument
        """
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_endorse_without_a_statement_and_then_endorse_with_statement(self):
        """
        If you have previously agreed to an argument without statement, then you try to agree with statement,
        it should update the existing agreement reaction to have your new statement.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.ENDORSE.name,
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test agreement',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test agreement',
            user=user
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_disagree_without_statement_and_then_disagree_with_statement(self):
        """
        If you have previously disagreed to an argument without statement, then you try to disagree with a statement,
        it should update the existing disagreement reaction to have your new statement.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.DISAGREE.name,
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test agreement',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content='test agreement',
            user=user
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_endorse_with_statement_and_disagree_with_statement(self):
        """
        test argument for Endorse with statement and then Disagree with statement
        response should be successfull
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.ENDORSE.name,
                   'content': 'test Endorse',
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test disagree',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse'
        ).count(), 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content='test disagree'
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 2)

    def test_endorse_without_a_statement_and_then_disagree_with_statement(self):
        """
        If you're trying to disagree to an argument that already has an agreement reaction without statement,
        and you don't provide both agreement and disagreement statements, it should respond with bad request.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.ENDORSE.name,
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test disagree',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disagree_without_a_statement_and_then_agree_with_statement(self):
        """
        If you're trying to agree to an that already has an disagreement reaction without statement,
        and you don't provide both agreement and disagreement statements, it should respond with bad request.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.DISAGREE.name,
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test agree',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endorse_and_endorse(self):
        """
        test argument for Endorse and then Endorse
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse 1',
                              'argument_id': argument.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse 2',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse 1'
        ).count(), 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse 2'
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 2)

    def test_applaud_and_endorse(self):
        """
        test argument for Applaud and then Endorse
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse'
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_applaud_and_endorse_and_disagree(self):
        """
        test argument for Applaud, Endorse and then Disagree
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.ENDORSE.name,
                   'content': 'test Endorse',
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test Disagree',
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse'
        ).count(), 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content='test Disagree'
        ).count(), 1)
        self.assertEqual(argument.argument_reactions.count(), 2)

    def test_agree_without_statement_and_then_try_disagree_without_statement(self):
        """
        If you try to agree without statement and then try to disagree without statement
        it should toggle the agreement statement to disagreement statement
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)
        self.assertEqual(response.data['stats']['disagree']['count'], 0)

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 0)
        self.assertEqual(response.data['stats']['disagree']['count'], 1)

    def test_disagree_without_statement_with_already_existing_agreement_without_statement_from_different_user(self):
        """
        You should be allowed to disagree without statement with an already existing agreement without statement.
        """
        create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")
        View.objects.create(parent_argument=argument,
                            reaction_type=ReactionType.ENDORSE.name,
                            type=ViewType.ARGUMENT_REACTION.name,
                            user=proposition)

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'argument_id': argument.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)
        self.assertEqual(response.data['stats']['disagree']['count'], 1)
        self.assertTrue(response.data['stats']['disagree']['selected'])

    def test_agree_without_statement_and_then_try_to_agree_without_statement_again(self):
        """
        If you try to agree without statement to an argument that already has an agreement without statement,
        it should be toggled.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.ENDORSE.name,
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
        ).count(), 0)
        self.assertEqual(argument.argument_reactions.count(), 0)

    def test_disagree_without_statement_and_then_try_to_disagree_without_statement_again(self):
        """
        If you try to agree without statement to an argument that already has an agreement without statement,
        it should be toggled.
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        self.post({'type': ReactionType.DISAGREE.name,
                   'argument_id': argument.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.ARGUMENT_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
        ).count(), 0)
        self.assertEqual(argument.argument_reactions.count(), 0)

    def test_moogter_argument_reaction_on_live_moogt(self):
        """
        If a moogter is trying to react on an argument with statement while the
        moogt they are participating in is live the request should fail
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test argument",
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(argument.argument_reactions.count(), 0)

    def test_moogter_argument_reaction_on_ended_moogt(self):
        """
        If a moogter is trying to react on an argument while the moogt they are
        participating in is ended the request should be successfull
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "argument", moogt_has_ended=True)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_moogter_argument_reaction_without_content(self):
        """
        If a moogter is trying to react on an argument while the moogt they are
        participating in is live the request should fail
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_non_moogter_argument_reaction_on_live_moogt(self):
        """
        If a non moogter is trying to react on an argument of a moogt while it is live
        the request should be successfull
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_non_moogter_argument_reaction_on_ended_moogt(self):
        """
        If a non moogter is trying to react on an argument of a moogt while it is ended
        the request should be successfull
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(
            proposition, "test argument", moogt_has_ended=True)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 1)

    def test_endorse_with_one_user_and_endorse_with_another_user(self):
        """
        If a user endorses an argument without statement and another user endorses the same
        argument without statement it should not delete the first users endorsement reaction
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        user_1 = create_user_and_login(self, 'test_username', 'password')
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 2)

    def test_reaction_from_a_moogter_creates_an_activity(self):
        """
        If a moogter on an argument reacts without statement to the argument of an opponent
        an ENDORSEMENT/DISAGREEMENT Moogt Activity object is created
        """
        user = create_user_and_login(self)
        proposition = create_user("username", "password")

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=user)
        argument = create_argument(proposition, 'test argument', moogt=moogt)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 1)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(MoogtActivity.objects.count(), 1)
        self.assertEqual(MoogtActivity.objects.first().type,
                         MoogtActivityType.ENDORSEMENT.name)
        self.assertEqual(MoogtActivity.objects.first().status,
                         ActivityStatus.ACCEPTED.value)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(
            MoogtActivityBundle.objects.first().activities.count(), 1)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(argument.argument_reactions.count(), 0)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(MoogtActivity.objects.count(), 0)
        self.assertEqual(
            MoogtActivityBundle.objects.first().activities.count(), 0)

    def test_reaction_from_a_non_moogter_does_not_create_a_status_argument(self):
        """
        If a non moogter reacts without statement to the argument of a moogter a status
        object of type argument should not be created
        """
        user = create_user_and_login(self)
        proposition = create_user("proposition", "password")
        opposition = create_user("opposition", "password")

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=opposition)
        prop_argument = create_argument(
            proposition, 'test argument', moogt=moogt)
        opp_argument = create_argument(
            opposition, 'test argument 2', moogt=moogt)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': prop_argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # only the arguments created by the moogters
        self.assertEqual(Argument.objects.count(), 2)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': opp_argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 2)

    def test_moogter_toggling_reactions(self):
        """
        If moogter toggles their reaction on an opponents arguments then it should also toggle the
        activity
        """
        proposition = create_user_and_login(self)
        opposition = create_user("opposition", "password")

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=opposition)
        opp_argument = create_argument(
            opposition, 'test argument 2', moogt=moogt)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'argument_id': opp_argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # only the arguments created by the moogters
        self.assertEqual(MoogtActivity.objects.count(), 1)
        self.assertEqual(MoogtActivity.objects.first().type,
                         MoogtActivityType.ENDORSEMENT.name)
        self.assertEqual(MoogtActivity.objects.first().status,
                         ActivityStatus.ACCEPTED.value)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(
            MoogtActivityBundle.objects.first().activities.count(), 1)

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'argument_id': opp_argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(MoogtActivity.objects.count(), 1)
        self.assertEqual(MoogtActivity.objects.first().type,
                         MoogtActivityType.DISAGREEMENT.name)
        self.assertEqual(MoogtActivity.objects.first().status,
                         ActivityStatus.ACCEPTED.value)
        self.assertEqual(MoogtActivityBundle.objects.count(), 1)
        self.assertEqual(
            MoogtActivityBundle.objects.first().activities.count(), 1)

    def test_version_2_api(self):
        """
        Should return the newly reacted object by expanding the parent.
        """
        create_user_and_login(self)
        proposition = create_user("username", "password")
        argument = create_argument(proposition, "test argument")
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'argument_id': argument.id},
                             version='v2')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['parent']['id'], argument.id)


class ArgumentCommentCreateAPITests(APITestCase):
    def post(self, body=None):
        url = reverse('api:arguments:comment_argument',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_successfully_create_comment(self):
        """
        Test if you can successfully comment on Argument
        """
        commenter = create_user_and_login(self)
        user = create_user("username", "password")
        argument = create_argument(user, "test argument")

        response = self.post({
            'argument_id': argument.id,
            'comment': 'test comment'
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(argument.comments_count(), 1)
        self.assertEqual(user.notifications.count(), 1)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.argument_comment)

    def test_reply_to_comment(self):
        """
        Test if you can successfully reply to a comment on an argument
        """
        commenter = create_user_and_login(self)
        user = create_user("username", "password")
        argument = create_argument(user, "test argument")

        comment = create_comment(argument, user, "test comment")

        response = self.post({
            'argument_id': argument.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(user.notifications.count(), 1)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.argument_comment)

    def test_moogter_reply_to_comment_in_live_moogt(self):
        """
        Test if a moogter replies on a comment in an ongoing moogt it should fail
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument")

        comment = create_comment(argument, user, "test comment")

        response = self.post({
            'argument_id': argument.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_moogter_reply_to_comment_in_ended_moogt(self):
        """
        Test if a moogter replies on a comment in an ended moogt it should be able to
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument", moogt_has_ended=True)

        comment = create_comment(argument, user, "test comment")
        response = self.post({
            'argument_id': argument.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class ListArgumentCommentsAPITests(APITestCase):
    def get(self, argument_id, limit=3, offset=0):
        url = reverse('api:arguments:list_comment', kwargs={'version': 'v1', 'pk': argument_id}) + '?limit=' + str(
            limit) + '&offset=' + str(offset)
        return self.client.get(url, format='json')

    def reply(self, body=None):
        url = reverse('api:arguments:comment_argument',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_list_comments(self):
        """
        Test if you can successfully list all comments of an argument
        """
        user = create_user_and_login(self)

        argument = create_argument(user, "test argument")

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
        argument = create_argument(user, "test argument")

        comment = create_comment(argument, user, "test comment")

        self.reply({
            'argument_id': argument.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        response = self.get(argument.id, limit=5)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)


class ListArgumentsAPITests(APITestCase):
    def get(self, moogt_id, cursor=None):
        url = reverse('api:arguments:list_argument', kwargs={
                      'version': 'v1', 'pk': moogt_id})

        if cursor:
            url += '?cursor=' + str(cursor)

        return self.client.get(url, format='json')

    def test_list_arguments(self):
        """
        Test if you can successfully list all arguments in a moogt
        """
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user)
        arguments = []
        for i in range(11):
            arguments.append(create_argument(
                user, f"argument {i}", moogt=moogt))

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], arguments[10].id)

    def test_list_arguments_as_new_user_without_before_and_after_query_parameter(self):
        """
        Test if you can successfully list all latest arguments in a moogt if
        no after and before arguments are provided and then try to navigate using the response of the first request
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)

        arguments = []
        for i in range(11):
            arguments.append(create_argument(
                user, f"argument {i}", moogt=moogt))

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], arguments[10].id)

        next_link_cursor = response.data['next'].split('?')[1].split('=')[1]

        response = self.get(moogt.id, cursor=next_link_cursor)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], arguments[0].id)
        self.assertIsNone(response.data['next'])

    def test_list_arguments_with_a_moogt_following_user(self):
        """
        If a user is following a moogt but does not have a cursor pointing to the
        last read at position it should return the latest arguments of the moogt
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)
        moogt.followers.add(user)

        arguments = []
        for i in range(11):
            arguments.append(create_argument(
                user, f"argument {i}", moogt=moogt))

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], arguments[10].id)

    def test_list_arguments_with_a_moogt_following_user_and_read_position_on_top(self):
        """
        If the last read at position is at the top of the moogt and there is no unread cards
        in the moogt the endpoint should be able to handle this use case
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)
        moogt.followers.add(user)
        read_by = ReadBy.objects.create(
            user=user, moogt=moogt, latest_read_at=timezone.now())

        arguments = []
        for i in range(11):
            arguments.append(create_argument(
                user, f"argument {i}", moogt=moogt))

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][-1]['id'], arguments[0].id)

    def test_list_arguments_with_no_arguments(self):
        """
        When there are no arguments to be shown the field in the response
        should be an empty array
        """
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user)

        moogt.followers.add(user)
        read_by = ReadBy(moogt=moogt, user=user)
        read_by.latest_read_at = timezone.now()
        read_by.save()

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_list_arguments_with_replies(self):
        """
        Test if you can successfully list all arguments in a moogt with their replies attached
        """
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user)

        argument = create_argument(user, "argument", moogt=moogt)
        reply_to = create_argument(
            user, "argument", moogt=moogt, reply_to=argument)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_existing_moogt(self):
        """
        Test if you can successfully respond to non existing moogt
        """
        user = create_user_and_login(self)

        response = self.get(404)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_view_edited_arguments(self):
        """
        Test if you can successfully add modified arguments in the response
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)

        argument = create_argument(
            user, "argument", moogt=moogt, modified_child_argument="edited argument")
        child_argument = argument.modified_child
        child_argument.modified_parent = None
        child_argument.is_edited = True
        child_argument.save()
        argument.delete()

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results']
                         [0]['object']['is_edited'], True)
        self.assertEqual(response.data['results'][0]
                         ['object']['argument'], 'edited argument')

    def test_list_arguments_for_non_moogters(self):
        """
        Listing arguments for non moogters must not have activities field not expanded
        """

        user = create_user("username", "password")
        moogt = create_moogt_with_user(proposition_user=user, opposition=True)
        argument = create_argument(user, "argument", moogt=moogt)
        create_argument_activity(
            user, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value, argument=argument)

        user = create_user_and_login(self)
        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            hasattr(response.data['results'][0]['object'], 'activities'))
        self.assertTrue(response.data['results']
                        [0]['object']['has_activities'])

    def test_list_arguments_for_moogters(self):
        """
        Listing argument for moogters must have activities field expanded
        """
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user)

        argument = create_argument(user, "argument", moogt=moogt)
        activity = create_argument_activity(user, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['object']['activities'][0]['id'], activity.id)

    def test_list_arguments_with_images(self):
        """If there are images for the arguments they should be included in the response."""
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user)

        argument = create_argument(user, "argument", moogt=moogt)

        argument_image = ArgumentImage.objects.create(argument=argument)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['object']['images'][0]['id'], argument_image.id)

    def test_list_arguments_exclude_concluding_arguments(self):
        """
        Response should not inlcude concluding arguments
        """
        user = create_user_and_login(self)
        user_1 = create_user("username", "password")

        moogt = create_moogt_with_user(
            proposition_user=user, opposition=user_1, started_at_days_ago=1)

        argument1 = create_argument(user, "argument1", moogt=moogt)
        argument2 = create_argument(user, "argument2", moogt=moogt)
        argument3 = create_argument(
            user, "argument3", moogt=moogt, type=ArgumentType.CONCLUDING.name)

        response = self.get(moogt.id)

        self.assertEqual(response.data['results'][0]['id'], argument2.id)
        self.assertEqual(response.data['results'][1]['id'], argument1.id)

    def test_user_has_commented(self):
        """
        If a user has commented on an argument then the stats object should indicate that
        """
        user = create_user_and_login(self)
        user_1 = create_user("username", "password")

        moogt = create_moogt_with_user(
            proposition_user=user, opposition=user_1, started_at_days_ago=1)
        argument = create_argument(user, "argument1", moogt=moogt)

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['object']['stats']['comment']['selected'], False)

        comment = create_comment(argument, user, "test comment")

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'][0]['object']['stats']['comment']['selected'], True)

    def test_list_arguments_a_user_follows(self):
        """
        If a user is following a moogt then it should get the latest unread cards with a minimum of
        2 read cards on the top of the list
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)
        arguments = []

        for i in range(20):
            arguments.append(create_argument(
                user, f"argument {i}", moogt=moogt))

        moogt.followers.add(user)

        read_by = ReadBy(moogt=moogt, user=user)
        # read argument indexed by 5
        read_by.latest_read_at = arguments[5].created_at
        read_by.save()

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][-1]['id'], arguments[5].id)

    def test_argument_stats_includes_moogter_reactions(self):
        """Make sure the argument stats includes moogter reactions as well as non moogter reactions."""
        user = create_user_and_login(self)
        user_1 = create_user("username", "password")

        moogt = create_moogt_with_user(
            proposition_user=user, opposition=user_1, started_at_days_ago=1)
        argument = create_argument(user, "argument1", moogt=moogt)
        reaction_argument: Argument = create_argument(
            user, 'reaction argument', moogt=moogt)
        reaction_argument.react_to = argument
        reaction_argument.reaction_type = ArgumentReactionType.ENDORSEMENT.name
        reaction_argument.save()

        response = self.get(moogt.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][1]
                         ['object']['stats']['endorse']['count'], 1)
        self.assertTrue(response.data['results'][1]
                        ['object']['stats']['endorse']['selected'])
        self.assertEqual(
            response.data['results'][1]['object']['stats']['endorse']['percentage'], 100)

        disagreement_reaction: Argument = create_argument(
            user, 'reaction argument', moogt=moogt)
        disagreement_reaction.react_to = argument
        disagreement_reaction.reaction_type = ArgumentReactionType.DISAGREEMENT.name
        disagreement_reaction.save()

        response = self.get(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][2]
                         ['object']['stats']['disagree']['count'], 1)
        self.assertTrue(response.data['results'][2]
                        ['object']['stats']['disagree']['selected'])
        self.assertEqual(
            response.data['results'][2]['object']['stats']['disagree']['percentage'], 50)

    # def test_return_mixed_content_of_moogt_detail(self):
    #     """
    #     Arguments, MoogtActivity and MoogtStatus are returned in the results sort by their respective
    #     sort_date parameter
    #     """
    #     user = create_user_and_login(self)
    #     moogt = create_moogt_with_user(
    #         proposition_user=user, opposition=True, started_at_days_ago=1)

    #     # page 2
    #     bundle1 = MoogtActivityBundle.objects.create(moogt=moogt)
    #     activity1 = MoogtActivity.objects.create(user=user,
    #                                              moogt=moogt,
    #                                              bundle=bundle1,
    #                                              status=ActivityStatus.PENDING.value,
    #                                              type=MoogtActivityType.PAUSE_REQUEST.name)

    #     argument1 = create_argument(user, 'argument 1', moogt=moogt)

    #     status1 = MoogtStatus.objects.create(user=user,
    #                                          moogt=moogt,
    #                                          status=MoogtStatus.STATUS.paused)
    #     # page 1
    #     argument2 = create_argument(user, 'argument 2', moogt=moogt)

    #     status2 = MoogtStatus.objects.create(user=user,
    #                                          moogt=moogt,
    #                                          status=MoogtStatus.STATUS.auto_paused)

    #     argument3 = create_argument(user, 'argument 3', moogt=moogt)

    #     response = self.get(moogt.id)

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)

    #     self.assertEqual(response.data['results'][0]['type'], 'argument')
    #     self.assertEqual(response.data['results'][0]['id'], argument3.id)
    #     self.assertEqual(response.data['results'][1]['type'], 'status')
    #     self.assertEqual(response.data['results'][1]['id'], status2.id)
    #     self.assertEqual(response.data['results'][2]['type'], 'argument')
    #     self.assertEqual(response.data['results'][2]['id'], argument2.id)

    #     self.assertEqual(response.data['results'][3]['type'], 'status')
    #     self.assertEqual(response.data['results'][3]['id'], status1.id)
    #     self.assertEqual(response.data['results'][4]['type'], 'argument')
    #     self.assertEqual(response.data['results'][4]['id'], argument1.id)
    #     self.assertEqual(response.data['results'][5]['type'], 'bundle')
    #     self.assertEqual(response.data['results'][5]['id'], bundle1.id)

    def test_list_argument_with_reactions(self):
        """
        Should indicate to clients with has_reaction to know whether or not it has
        reaction with statement.
        """
        user = create_user_and_login(self)
        moogt = create_moogt_with_user(proposition_user=user)

        argument = create_argument(user, 'argument 1', moogt=moogt)

        response = self.get(moogt.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['results']
                         [0]['object']['has_reactions'])

        # Has reaction without statement
        argument.argument_reactions.create(reaction_type=ReactionType.ENDORSE.name,
                                           type=ViewType.ARGUMENT_REACTION.name,
                                           user=user)
        response = self.get(moogt.id)
        self.assertFalse(response.data['results']
                         [0]['object']['has_reactions'])

        argument.argument_reactions.create(reaction_type=ReactionType.ENDORSE.name,
                                           type=ViewType.ARGUMENT_REACTION.name,
                                           content='test content',
                                           user=user)

        response = self.get(moogt.id)

        self.assertEqual(response.data['results'][0]['id'], argument.id)
        self.assertTrue(response.data['results'][0]['object']['has_reactions'])

        argument.argument_reactions.all().delete()

        argument.moogter_reactions.create(argument='test argument',
                                          reaction_type=ArgumentReactionType.DISAGREEMENT.name,
                                          moogt=moogt,
                                          user=user)

        response = self.get(moogt.id)
        self.assertEqual(response.data['results'][1]['id'], argument.id)
        self.assertTrue(response.data['results'][1]['object']['has_reactions'])


class ListConcludingArgumentsApiViewTests(APITestCase):
    def get(self, moogt_id, limit=3, offset=0):
        url = reverse('api:arguments:list_concluding_argument',
                      kwargs={'version': 'v1', 'pk': moogt_id}) + '?limit=' + str(
            limit) + '&offset=' + str(offset)
        return self.client.get(url, format='json')

    def test_successfully_return_concluding_arguments(self):
        """
        If a moogt has concluding arguments it should successfully return the concluding arguments
        """
        proposition = create_user_and_login(self)
        opposition = create_user("username", "password")

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=opposition, started_at_days_ago=1)

        argument1 = create_argument(
            proposition, "argument3", moogt=moogt, type=ArgumentType.CONCLUDING.name)
        argument2 = create_argument(
            opposition, "argument3", moogt=moogt, type=ArgumentType.CONCLUDING.name)

        response = self.get(moogt.id, limit=3, offset=0)

        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], argument2.id)
        self.assertEqual(response.data['results'][1]['id'], argument1.id)

    def test_exclude_normal_arguments(self):
        """
        Response should only include the concluding arguments
        """
        proposition = create_user_and_login(self)
        opposition = create_user("username", "password")

        moogt = create_moogt_with_user(
            proposition_user=proposition, opposition=opposition, started_at_days_ago=1)

        argument1 = create_argument(proposition, "argument2", moogt=moogt)
        argument2 = create_argument(
            proposition, "argument3", moogt=moogt, type=ArgumentType.CONCLUDING.name)
        argument3 = create_argument(
            opposition, "argument3", moogt=moogt, type=ArgumentType.CONCLUDING.name)

        response = self.get(moogt.id, limit=3, offset=0)

        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], argument3.id)
        self.assertEqual(response.data['results'][1]['id'], argument2.id)


class CreateEditRequestApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:arguments:request_edit', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_success(self):
        """
        Test if you can successfully create an edit request for an argument
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(user, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument'})

        activity = ArgumentActivity.objects.first()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        argument.refresh_from_db()
        self.assertEqual(argument.modified_child.argument,
                         'test edit requested argument')
        self.assertEqual(argument.is_edited, False)
        self.assertEqual(
            response.data['modified_child']['argument'], 'test edit requested argument')
        self.assertEqual(response.data['modified_child']['is_edited'], True)
        self.assertEqual(activity.actor, user_1)
        self.assertEqual(user_1.notifications.count(), 1)
        self.assertEqual(user_1.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)

    def test_success_if_moderator(self):
        """Test if the moderator can create an edit request for an argument"""

        moderator = create_user_and_login(self)
        user_1 = create_user("username", "password")
        user = create_user("username2", "password")

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        moogt.set_moderator(moderator)
        moogt.save()

        argument = create_argument(moderator, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        argument.refresh_from_db()
        self.assertEqual(argument.modified_child.argument,
                         'test edit requested argument')
        self.assertEqual(argument.is_edited, False)
        self.assertEqual(
            response.data['modified_child']['argument'], 'test edit requested argument')
        self.assertEqual(response.data['modified_child']['is_edited'], True)
        self.assertEqual(user_1.notifications.count(), 1)
        self.assertEqual(user_1.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)
        self.assertEqual(user.notifications.count(), 2)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)

    def test_create_request_not_owned_argument_for_moderator(self):
        """
        Test if an edit request is made by a moderator which is owned by another moogter
        """

        moderator = create_user_and_login(self)
        user_1 = create_user("username", "password")
        user = create_user("username2", "password")

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        moogt.set_moderator(moderator)
        moogt.save()

        argument = create_argument(user, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument'})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_edit_request_twice(self):
        """
        If an argument has already has a pending edit request sending another edit request should fail
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(user, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument 2'})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ArgumentActivity.objects.count(), 1)

    def test_no_argument_id(self):
        """
        If no parent argument id is passed then request should fail
        """
        user = create_user_and_login(self)

        response = self.post({'argument': 'test edit requested argument'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_argument(self):
        """
        If edit request body is empty then request should fail
        """
        user = create_user_and_login(self)

        argument = create_argument(user, "argument")

        response = self.post({'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_request_with_a_non_moogter(self):
        """
        If edit request was made by a non moogter request should fail
        """
        user = create_user_and_login(self)
        user_1 = create_user("username", "password")

        argument = create_argument(user_1, "argument")

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_request_with_original_no_image_and_edited_containing_image(self):
        """
        if edit request was made to an argument with no images and create an edit request with
        image then the modified child should contain images
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(user, "argument", moogt=moogt)

        argument_image = ArgumentImage.objects.create()

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument',
                              'images': [argument_image.id]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Argument.objects.get(
            id=response.data['modified_child']['id']).images.count(), 1)

    def test_create_request_with_original_argument_with_image_and_edited_argument_with_unchanged_image(self):
        """
        If an edit request was made to an argument with image and the edit request has unchanged images then
        the modified child should have images of the original argument
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(user, "argument", moogt=moogt)

        argument_image = ArgumentImage.objects.create(argument=argument)

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument',
                              'images': [argument_image.id]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Argument.objects.get(
            id=response.data['modified_child']['id']).images.count(), 1)
        self.assertEqual(Argument.objects.get(id=response.data['modified_child']['id']).images.first().id,
                         argument_image.id)

    def test_create_request_with_original_argument_with_image_and_edited_argument_with_image(self):
        """
        If an edit request was made to an argument with image and the edit request also has images
        the modified cihld should have the images of the new images
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(user, "argument", moogt=moogt)

        argument_image = ArgumentImage.objects.create(argument=argument)
        argument_image_2 = ArgumentImage.objects.create()

        response = self.post({'argument_id': argument.id,
                              'argument': 'test edit requested argument',
                              'images': [argument_image_2.id]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Argument.objects.get(
            id=response.data['modified_child']['id']).images.count(), 1)
        self.assertEqual(Argument.objects.get(id=response.data['modified_child']['id']).images.first().id,
                         argument_image_2.id)


class CreateDeleteRequestApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:arguments:request_delete', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_success(self):
        """
        Test if you can successfully create a delete argument request
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        argument = create_argument(user, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ActivityStatus.PENDING.value)
        self.assertEqual(response.data['type'],
                         ArgumentActivityType.DELETE.value)
        self.assertEqual(response.data['argument_id'], argument.id)
        self.assertEqual(response.data['actor_id'], user_1.id)
        self.assertEqual(user_1.notifications.count(), 1)
        self.assertEqual(user_1.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)

    def test_success_if_moderator(self):
        """
        Test if moderator can successfully create a delete argument request in an argument
        """
        user_1 = create_user("username", "password")
        user = create_user("username2", "password")
        moderator = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        moogt.set_moderator(moderator)

        moogt.save()

        argument = create_argument(moderator, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ActivityStatus.PENDING.value)
        self.assertEqual(response.data['type'],
                         ArgumentActivityType.DELETE.value)
        self.assertEqual(response.data['argument_id'], argument.id)
        self.assertEqual(response.data['actor_id'], user_1.id)
        self.assertEqual(user_1.notifications.count(), 1)
        self.assertEqual(user_1.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)
        self.assertEqual(user.notifications.count(), 2)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)

    def test_delete_not_owned_argument_for_moderator(self):
        """
        Tests if the moderator is allowed to make delete request of other user owned argument
        """
        user_1 = create_user("username", "password")
        user = create_user("username2", "password")
        moderator = create_user_and_login(self)

        moogt = create_moogt_with_user(proposition_user=user,
                                       opposition=user_1,
                                       resolution="test resolution",
                                       started_at_days_ago=1)

        moogt.set_moderator(moderator)

        moogt.save()

        argument = create_argument(user_1, "argument", moogt=moogt)

        response = self.post({'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ActivityStatus.PENDING.value)
        self.assertEqual(response.data['type'],
                         ArgumentActivityType.DELETE.value)
        self.assertEqual(response.data['argument_id'], argument.id)
        self.assertEqual(response.data['actor_id'], user_1.id)
        self.assertEqual(user_1.notifications.count(), 1)
        self.assertEqual(user_1.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)
        self.assertEqual(user.notifications.count(), 2)
        self.assertEqual(user.notifications.first().type,
                         NOTIFICATION_TYPES.argument_request)

    def test_no_argument_id(self):
        """
        If no argument id is provided then request should fail
        """
        user = create_user_and_login(self)
        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_not_owned_argument(self):
        """
        If a user tries to delete an argument that they do not own request should fail
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        argument = create_argument(user_1, "argument")

        response = self.post({'argument_id': argument.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DeleteRequestActionApiViewTests(APITestCase):
    @staticmethod
    def mock_notify_ws_clients_for_argument(arg, message_type):
        pass

    def post(self, body=None):
        url = reverse('api:arguments:request_delete_action',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_successfully_approve_delete_an_argument(self):
        """
        Test if you can successfully Approve the delete action for an argument
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)

        argument = create_argument(user_1, "argument", moogt=moogt)
        argument.argument_reactions.create(user=user, content=None)

        activity = create_argument_activity(user_1, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value,
                                            argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.ACCEPTED.value})

        activity.refresh_from_db()

        # this is the argument object that is displayed as a deleted argument
        # replacing the original argument
        argument = Argument.objects.first()

        resolved_notification = user_1.notifications.filter(
            type=NOTIFICATION_TYPES.argument_request_resolved)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(argument.activities.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.ACCEPTED.value)
        self.assertEqual(argument.type, ArgumentType.DELETED.name)
        self.assertEqual(resolved_notification.count(), 1)
        self.assertEqual(resolved_notification.first().verb, 'approved')
        self.assertEqual(resolved_notification.first().data.get(
            'data').get('argument', None), None)
        self.assertEqual(View.objects.count(), 0)

        self.assertEqual(activity.actions.first().actor, user)
        self.assertEqual(activity.actions.first().action_type,
                         AbstractActivityAction.ACTION_TYPES.approve)

    def test_successfully_approve_delete_an_argument_by_moderator(self):
        """
        Test if you can successfully Approve the delete action for an argument by a moderator
        """
        user_1 = create_user("username1", "password")
        user = create_user("username", "password")
        moderator = create_user_and_login(self, "moderator", 'password')

        moogt = create_moogt_with_user(user_1, opposition=user)
        moogt.set_moderator(moderator)

        argument = create_argument(user, "argument", moogt=moogt)
        argument.argument_reactions.create(user=user_1, content=None)

        activity = create_argument_activity(user_1, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value,
                                            argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.ACCEPTED.value})

        activity.refresh_from_db()

        # this is the argument object that is displayed as a deleted argument
        # replacing the original argument
        argument = Argument.objects.first()

        resolved_notification = user_1.notifications.filter(
            type=NOTIFICATION_TYPES.argument_request_resolved)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(argument.activities.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.ACCEPTED.value)
        self.assertEqual(argument.type, ArgumentType.DELETED.name)
        self.assertEqual(resolved_notification.count(), 1)
        self.assertEqual(resolved_notification.first().verb, 'approved')
        self.assertEqual(resolved_notification.first().data.get(
            'data').get('argument', None), None)
        self.assertEqual(View.objects.count(), 0)

        self.assertEqual(activity.actions.first().actor, moderator)
        self.assertEqual(activity.actions.first().action_type,
                         AbstractActivityAction.ACTION_TYPES.approve)

    def test_successfully_decline_deleting_an_argument_without_moderator(self):
        """
        Test if you can successfully Decline the delete action for an argument
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)

        argument = create_argument(user_1, "argument", moogt=moogt)

        activity = create_argument_activity(user_1, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})

        activity.refresh_from_db()
        argument_2 = Argument.objects.first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(argument.id, argument_2.id)
        self.assertEqual(activity.status, ActivityStatus.DECLINED.value)
        self.assertEqual(user_1.notifications.filter(
            type=NOTIFICATION_TYPES.argument_request_resolved).count(), 1)
        self.assertEqual(user_1.notifications.filter(type=NOTIFICATION_TYPES.argument_request_resolved).first().verb,
                         'declined')

        self.assertEqual(activity.actions.first().actor, user)
        self.assertEqual(activity.actions.first().action_type,
                         AbstractActivityAction.ACTION_TYPES.decline)

    def test_successfully_decline_deleting_an_argument_with_moderator(self):
        """
        Returns waiting if there is moderator in a moogt when declining the request,
        then returns the status changes to decline after the other moogter declines         
        """
        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        proposition = create_user('proposition', 'pass123')
        moogt = create_moogt_with_user(proposition, opposition=opposition)
        moogt.set_moderator(moderator)
        moogt.save()

        argument = create_argument(proposition, "argument", moogt=moogt)

        activity = create_argument_activity(proposition, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(activity.actions.first().actor, moderator)
        self.assertEqual(activity.actions.first().action_type,
                         AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(opposition)
        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        activity.refresh_from_db()
        self.assertEqual(activity.status, ActivityStatus.DECLINED.value)
        self.assertEqual(activity.actions.last().actor, opposition)
        self.assertEqual(activity.actions.last().action_type,
                         AbstractActivityAction.ACTION_TYPES.decline)

    def test_successfully_cancelling_delete_argument_request(self):
        """Test if you can successfully Cancel the delete action for an argument"""

        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)

        argument = create_argument(user, "argument", moogt=moogt)

        activity = create_argument_activity(user, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})

        activity.refresh_from_db()
        argument.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.CANCELLED.value)

    def test_no_activity_id(self):
        """
        If no Activity id is supplied request should fail
        """
        user = create_user_and_login(self)
        activity = create_argument_activity(
            user, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value)

        response = self.post({'status': ActivityStatus.ACCEPTED.value})
        activity.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_status(self):
        """
        If no status is supplied request should fail
        """
        user = create_user_and_login(self)
        activity = create_argument_activity(
            user, ArgumentActivityType.DELETE.value, ActivityStatus.PENDING.value)

        response = self.post({'activity_id': activity.id})
        activity.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_none_existing_activity(self):
        """
        If a none existing activity id is supplied request should fail
        """
        user = create_user_and_login(self)

        response = self.post(
            {'activity_id': '1', 'status': ActivityStatus.ACCEPTED.value})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EditRequestActionApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:arguments:request_edit_action',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_successfully_approve_editing_an_argument(self):
        """
        Test if you can successfully approve an edit request for an argument
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)

        argument = create_argument(
            user_1, "argument", moogt=moogt, modified_child_argument="edited argument")

        activity = create_argument_activity(user_1, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.ACCEPTED.value})

        activity.refresh_from_db()

        # this is the argument object that is displayed as an Edited argument
        # replacing the original argument
        argument = Argument.objects.first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.ACCEPTED.value)
        self.assertEqual(argument.type, ArgumentType.NORMAL.name)
        self.assertEqual(argument.activities.count(), 1)
        self.assertEqual(argument.argument, "edited argument")

    def test_successfully_approve_editing_an_argument_by_moderator(self):
        """
        Test if you can successfully approve an edit request for an argument by moderator
        """
        user_1 = create_user("username1", "password")
        user = create_user("username", "password")
        moderator = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)
        moogt.set_moderator(moderator)

        argument = create_argument(
            user_1, "argument", moogt=moogt, modified_child_argument="edited argument")

        activity = create_argument_activity(user_1, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.ACCEPTED.value})

        activity.refresh_from_db()

        # this is the argument object that is displayed as an Edited argument
        # replacing the original argument
        argument = Argument.objects.first()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.ACCEPTED.value)
        self.assertEqual(argument.type, ArgumentType.NORMAL.name)
        self.assertEqual(argument.activities.count(), 1)
        self.assertEqual(argument.argument, "edited argument")

    def test_editing_an_argument_with_reactions(self):
        """
        If an argument had reactions when a moogter approves an edit request on it
        the react_to argument should be the edited argument.
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)

        argument = create_argument(
            user_1, "argument", moogt=moogt, modified_child_argument="edited argument")

        reaction = create_argument(user, "argument", moogt=moogt)
        reaction.react_to = argument
        reaction.save()

        activity = create_argument_activity(user_1,
                                            ArgumentActivityType.EDIT.value,
                                            ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.ACCEPTED.value})

        # this is the argument object that is displayed as an Edited argument
        # replacing the original argument
        edited = Argument.objects.first()

        activity.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # the edited argument and the reaction argument
        self.assertEqual(Argument.objects.count(), 2)
        self.assertEqual(activity.status, ActivityStatus.ACCEPTED.value)
        self.assertEqual(edited.type, ArgumentType.NORMAL.name)
        self.assertEqual(edited.activities.count(), 1)
        self.assertEqual(edited.moogter_reactions.count(), 1)
        self.assertEqual(edited.moogter_reactions.first().id, reaction.id)
        self.assertEqual(edited.argument, "edited argument")

    def test_successfully_decline_editing_an_argument_without_moderator(self):
        """
        Test if you can succesfully decline an edit request for an argument
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)

        argument = create_argument(
            user_1, "argument", moogt=moogt, modified_child_argument="edited argument")

        activity = create_argument_activity(user_1, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})

        activity.refresh_from_db()
        argument.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.DECLINED.value)
        self.assertEqual(argument.modified_child, None)

    def test_successfully_decline_editing_an_argument_with_moderator(self):
        """
        Returns waiting if there is moderator in a moogt when declining the request,
        then returns the status changes to decline after the other moogter declines         
        """

        moderator = create_user_and_login(self, 'moderator', 'pass123')
        opposition = create_user('opposition', 'pass123')
        proposition = create_user('proposition', 'pass123')
        moogt = create_moogt_with_user(proposition, opposition=opposition)
        moogt.set_moderator(moderator)
        moogt.save()

        argument = create_argument(proposition, "argument", moogt=moogt)

        activity = create_argument_activity(proposition, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(activity.actions.first().actor, moderator)
        self.assertEqual(activity.actions.first().action_type,
                         AbstractActivityAction.ACTION_TYPES.waiting)

        self.client.logout()

        self.client.force_login(opposition)
        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        activity.refresh_from_db()
        self.assertEqual(activity.status, ActivityStatus.DECLINED.value)
        self.assertEqual(activity.actions.last().actor, opposition)
        self.assertEqual(activity.actions.last().action_type,
                         AbstractActivityAction.ACTION_TYPES.decline)

    def test_successfully_cancelled_editing_card_argument(self):
        """Tests if you can successfully cancel on edit request for an argument"""

        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, opposition=user)
        argument = create_argument(
            user, "argument", moogt=moogt, modified_child_argument="edited argument")

        activity = create_argument_activity(user, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)
        response = self.post(
            {'activity_id': activity.pk, 'status': ActivityStatus.DECLINED.value})

        activity.refresh_from_db()
        argument.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Argument.objects.count(), 1)
        self.assertEqual(activity.status, ActivityStatus.CANCELLED.value)

    def test_no_activity_id(self):
        """
        If no activity id is supplied then request should fail
        """
        user = create_user_and_login(self)
        response = self.post({'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_status(self):
        """
        If no status supplied the request should fail
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)
        argument = create_argument(
            user_1, "argument", modified_child_argument="edited argument")

        activity = create_argument_activity(user_1, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)

        response = self.post({'activity_id': activity.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approving_your_own_edit(self):
        """
        If a user is trying to approve their own edit request should fail
        """
        user = create_user_and_login(self)
        argument = create_argument(
            user, "argument", modified_child_argument="edited argument")

        activity = create_argument_activity(user, ArgumentActivityType.EDIT.value, ActivityStatus.PENDING.value,
                                            argument=argument)
        response = self.post({'activity_id': activity.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_existing_activity(self):
        """
        If a non existing activity is supplied request should fail
        """
        user = create_user_and_login(self)
        response = self.post(
            {'activity_id': 1, 'status': ActivityStatus.DECLINED.value})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ListArgumentActivityApiViewTests(APITestCase):
    def get(self, argument_id, limit=3, offset=0):
        url = reverse('api:arguments:list_activities', kwargs={'version': 'v1', 'pk': argument_id}) + '?limit=' + str(
            limit) + '&offset=' + str(offset)
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.argument = create_argument(self.user, 'test argument')

    def test_non_existing_argument(self):
        """
        Test if supplied argument is non existent
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_success(self):
        """
        Test if you can successfully list activities for an argument
        """
        activity = create_argument_activity(self.user, ArgumentActivityType.EDIT.name,
                                            ActivityStatus.PENDING.name, argument=self.argument)
        response = self.get(self.argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], activity.id)

    def test_no_activities(self):
        """
        Test if no activities exist for an argument an empty set should be returned
        """
        response = self.get(self.argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


class ArgumentDetailApiViewTests(APITestCase):
    def get(self, argument_id):
        url = reverse('api:arguments:argument_detail', kwargs={
                      'version': 'v1', 'pk': argument_id})
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.argument = create_argument(self.user, 'test argument')

    def test_non_existing_argument(self):
        """A request for a non existing argument should be dealt with a non found response."""
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_for_existing_argument(self):
        """A request for an existing should be dealt with a 2xx response."""
        response = self.get(self.argument.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['argument'], 'test argument')
        self.assertIsNotNone(response.data['moogt'])

    def test_get_argument_with_reaction(self):
        """Get detail of an argument with reactions"""
        user_1 = create_user("test_username", "password")

        rxn_view = create_view(user_1, 'test reaction')
        rxn_view.parent_argument = self.argument
        rxn_view.type = ViewType.ARGUMENT_REACTION.name
        rxn_view.reaction_type = ReactionType.ENDORSE.name
        rxn_view.save()

        response = self.get(self.argument.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)


class AdjacentArgumentsListApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt()
        opposition_user = create_user('opposition', 'pass123')
        moderator = create_user('moderator', 'pass123')
        self.moogt.set_moderator(moderator)
        self.moogt.set_proposition(self.user)
        self.moogt.set_opposition(opposition_user)
        self.moogt.save()
        self.argument1 = create_argument(
            argument='argument1', user=self.user, moogt=self.moogt)
        self.argument2 = create_argument(
            argument='argument2', user=self.user, moogt=self.moogt)
        self.argument3 = create_argument(
            argument='argument3', user=opposition_user, moogt=self.moogt)
        self.argument4 = create_argument(
            argument='argument4', user=self.user, moogt=self.moogt)
        self.argument5 = create_argument(
            argument='argument5', user=opposition_user, moogt=self.moogt)
        self.argument6 = create_argument(
            argument='argument6', user=moderator, moogt=self.moogt,  type=ArgumentType.MODERATOR_ARGUMENT.name)

    def get(self, argument_id):
        url = reverse('api:arguments:adjacent_arguments_list',
                      kwargs={'version': 'v1', 'pk': argument_id})
        return self.client.get(url)

    def test_non_authenticated_user(self):
        """A non authorized user should get a non authorized response."""
        self.client.logout()
        response = self.get(self.argument1.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_argument(self):
        """For a non existing argument, it should respond with a not found response."""
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_it_should_get_next_and_previous_item(self):
        """It should get the next and previous items for a given argument."""
        response = self.get(self.argument2.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['prev_count'], 1)
        self.assertEqual(response.data['next_count'], 4)
        self.assertEqual(response.data['prev_results']
                         [0]['id'], self.argument1.id)
        self.assertTrue(response.data['prev_results']
                        [0]['proposition_created'])
        self.assertEqual(response.data['next_results']
                         [0]['id'], self.argument3.id)
        self.assertFalse(
            response.data['next_results'][0]['proposition_created'])

    def test_should_get_next_and_previous_item_for_moderator_type(self):
        """An argument should get previous and next item even if there is a moderator type argument in the middle"""

        response = self.get(self.argument5.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['prev_count'], 4)
        self.assertEqual(response.data['next_count'], 1)
        self.assertEqual(response.data['prev_results']
                         [0]['id'], self.argument4.id)
        self.assertEqual(response.data['next_results']
                         [0]['id'], self.argument6.id)

    def test_the_first_item_in_the_sequence(self):
        """If there are no elements before the element you're looking for then the count should be 0."""
        response = self.get(self.argument1.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['prev_count'], 0)
        self.assertEqual(response.data['next_count'], 5)
        self.assertEqual(response.data['next_results']
                         [0]['id'], self.argument2.id)
        self.assertEqual(response.data['next_results']
                         [0]['proposition_created'], True)
        self.assertEqual(response.data['next_results']
                         [1]['id'], self.argument3.id)
        self.assertEqual(response.data['next_results']
                         [1]['proposition_created'], False)
        self.assertEqual(len(response.data['next_results']), 2)

    def test_the_last_item_in_the_sequence(self):
        """If there are no elements after the element you're looking for then the count should be 0."""
        response = self.get(self.argument6.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['prev_count'], 5)
        self.assertEqual(response.data['next_count'], 0)
        self.assertEqual(response.data['prev_results']
                         [0]['id'], self.argument4.id)
        self.assertEqual(response.data['prev_results']
                         [0]['proposition_created'], True)
        self.assertEqual(response.data['prev_results']
                         [1]['id'], self.argument5.id)
        self.assertEqual(response.data['prev_results']
                         [1]['proposition_created'], False)
        self.assertEqual(len(response.data['prev_results']), 2)
        self.assertEqual(len(response.data['next_results']), 0)

    def test_argument_that_is_not_in_the_same_moogt_will_not_be_included(self):
        """
        Arguments that are not in the same moogt as the one you're looking for will not be included in the response.
        """
        create_argument(argument='test_argument', user=self.user)
        response = self.get(self.argument3.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['prev_count'], 2)
        self.assertEqual(response.data['next_count'], 3)


class UploadArgumentImageApiViewTests(APITestCase):
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
        url = reverse('api:arguments:upload_image', kwargs={'version': 'v1'})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """
        A non authenticated user should not be able to make an upload request.
        """
        self.client.logout()
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_an_image(self):
        """Upload an image to the endpoint."""
        image = generate_photo_file()
        response = self.post({'image': image})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ArgumentImage.objects.count(), 1)


class ReadArgumentApiViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:arguments:read_argument', kwargs={'version': 'v1'})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.moogt = create_moogt_with_user(
            self.user, opposition=True, resolution='test resolution')
        self.user.following_moogts.add(self.moogt)
        self.read_by = ReadBy(moogt=self.moogt, user=self.user)
        self.read_by.save()
        self.argument = create_argument(
            self.user, 'test argument', moogt=self.moogt)

    def test_successfully_read_arguments(self):
        """If a user follows a moogt it should be able to successfully read an argument in a moogt"""
        unread_cards_count = self.moogt.unread_cards_count(self.user)

        self.assertEqual(unread_cards_count, 1)
        response = self.post(
            {'moogt_id': self.moogt.id, 'latest_read_argument_id': self.argument.id})

        self.read_by.refresh_from_db()
        unread_cards_count = self.moogt.unread_cards_count(self.user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(unread_cards_count, 0)

    # def test_read_card_should_not_work_for_older_card(self):
    #     """
    #     If a user is trying to read a card that has been read before it should not move the last read at
    #     position to the older card
    #     """
    #     unread_cards_count = self.moogt.unread_cards_count(self.user)

    #     self.assertEqual(unread_cards_count, 1)
    #     argument2 = create_argument(
    #         self.user, 'test argument 2', moogt=self.moogt)

    #     response = self.post(
    #         {'moogt_id': self.moogt.id, 'latest_read_argument_id': argument2.id})

    #     self.read_by.refresh_from_db()

    #     unread_cards_count = self.moogt.unread_cards_count(self.user)

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(unread_cards_count, 0)

    #     response = self.post(
    #         {'moogt_id': self.moogt.id, 'latest_read_argument_id': self.argument.id})

    #     self.read_by.refresh_from_db()
    #     unread_cards_count = self.moogt.unread_cards_count(self.user)

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(unread_cards_count, 0)


class BrowseArgumentReactionsApiView(APITestCase):
    def get(self, argument_id, reaction_type, own=False):
        url = reverse('api:arguments:browse_argument_reactions',
                      kwargs={'pk': argument_id, 'version': 'v1'})
        url += f'?type={reaction_type}'
        if own:
            url += f'&own={json.dumps(own)}'
        return self.client.get(url)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.argument = create_argument(self.user, 'test arg')

        # Create reactions by non-moogters
        user_1 = create_user('user1', 'pass123')
        for i in range(5):
            View.objects.create(parent_argument=self.argument,
                                user=user_1,
                                content=f'{i}',
                                reaction_type=ReactionType.ENDORSE.name)

            View.objects.create(parent_argument=self.argument,
                                user=user_1,
                                content=f'{i}',
                                reaction_type=ReactionType.DISAGREE.name)

        # Create moogter reactions.
        Argument.objects.create(user=self.user,
                                react_to=self.argument,
                                moogt=self.argument.get_moogt(),
                                reaction_type=ArgumentReactionType.ENDORSEMENT.name)

        Argument.objects.create(user=self.user,
                                react_to=self.argument,
                                moogt=self.argument.get_moogt(),
                                reaction_type=ArgumentReactionType.DISAGREEMENT.name)

    def test_non_not_existing_argument_object(self):
        """Should get a not found response for an argument that doesn't exist."""
        response = self.get(404, ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_mooogter_reaction_with_type_endorse(self):
        """Get reactions with type endorse."""
        response = self.get(
            self.argument.id, ReactionType.ENDORSE.name, own=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['object_type'], 'moogter_reaction')
        self.assertIsNotNone(response.data['results'][0]['object'])
        self.assertEqual(response.data['results'][0]['object']
                         ['reaction_type'], ArgumentReactionType.ENDORSEMENT.name)

    def test_get_mooogter_reaction_with_type_disagree(self):
        """Get reactions with type disagree."""
        response = self.get(
            self.argument.id, ReactionType.DISAGREE.name, own=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['object_type'], 'moogter_reaction')
        self.assertIsNotNone(response.data['results'][0]['object'])
        self.assertEqual(response.data['results'][0]['object']
                         ['reaction_type'], ArgumentReactionType.DISAGREEMENT.name)

    def test_get_non_moogter_reaction_with_type_endorse(self):
        """Get non moogter reactions with type endorse."""
        response = self.get(self.argument.id, ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(response.data['results'][0]
                         ['object_type'], 'non_moogter_reaction')
        self.assertIsNotNone(response.data['results'][0]['object'])
        self.assertEqual(
            response.data['results'][0]['object']['reaction_type'], ReactionType.ENDORSE.name)

    def test_get_non_moogter_reaction_with_type_disagree(self):
        """Get non moogter reactions with type disagree."""
        response = self.get(self.argument.id, ReactionType.DISAGREE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(response.data['results'][0]
                         ['object_type'], 'non_moogter_reaction')
        self.assertIsNotNone(response.data['results'][0]['object'])
        self.assertEqual(response.data['results'][0]['object']
                         ['reaction_type'], ReactionType.DISAGREE.name)


class ReportArgumentApiViewTests(APITestCase):
    def post(self, argument_id, data=None):
        url = reverse('api:arguments:report_argument', kwargs={
                      'pk': argument_id, 'version': 'v1'})
        return self.client.post(url, data)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.argument = ArgumentFactory.create()

    def test_non_logged_in_user(self):
        """Should respond with a not-authorized response for non-logged in users."""
        self.client.logout()
        response = self.post(self.argument.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_argument(self):
        """Should respond with a not-found response for an argument that does not exist."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('api.mixins.ReportMixin.validate')
    def test_should_call_validate(self, mock_validate: MagicMock):
        """Should call the validate method to validate."""
        self.post(self.argument.id)
        mock_validate.assert_called()

    @patch('api.mixins.ReportMixin.notify_admins')
    def test_notify_admins(self, mock_validate: MagicMock):
        """Should notify admins."""
        self.post(self.argument.id, {
                  'link': 'https://moogter.link', 'reason': 'test reason'})
        mock_validate.assert_called_once()

    def test_should_create_a_report(self):
        """Should create a report model for the argument."""
        response = self.post(self.argument.id, {
                             'link': 'https://moogter.com', 'reason': 'test reason'})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        argument_report = ArgumentReport.objects.all().first()
        self.assertIsNotNone(argument_report)
        self.assertEqual(argument_report.reported_by, self.user)
        self.assertIsNotNone(argument_report.argument)
