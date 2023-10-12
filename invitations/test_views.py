# Create your tests here.
from django.urls import reverse
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from django.contrib.contenttypes.models import ContentType

from api.enums import InvitationType
from api.tests.tests import create_user_and_login
from api.tests.utility import create_user_and_login, create_user, create_moogt_with_user, create_invitation
from chat.models import InvitationMessage, MessageSummary
from invitations.models import Invitation
from meda.enums import InvitationStatus
from meda.tests.test_models import create_moogt
from api.tests.utility import create_moderator_invitation
from invitations.models import ModeratorInvitation
from meda.enums import ModeratorInvititaionStatus
from chat.models import Conversation, ModeratorInvitationMessage, Participant
from moogts.models import Moogt, MoogtBanner
from users.models import MoogtMedaUser
from notifications.models import Notification


class RecentlyInvitedApiViewTests(APITestCase):
    def get(self):
        url = reverse('api:invitations:recent_invitation',
                      kwargs={'version': 'v1'})
        return self.client.get(url)

    def test_success(self):
        """
        test successfully retrieve recently invited user
        """

        user = create_user_and_login(self)
        moogt_invitee = create_user("invitee", "password")

        moogt = create_moogt_with_user(user, resolution="test resolution")

        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       invitee=moogt_invitee, inviter=moogt.get_proposition())

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_retrieve_two_recently_invited(self):
        """
        test successfully retrieve recently invited two users
        """

        user = create_user_and_login(self)
        moogt_invitee = create_user("invitee", "password")
        moogt_invitee_2 = create_user("invitee_2", "password")

        moogt = create_moogt_with_user(user, resolution="test resolution")

        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       invitee=moogt_invitee, inviter=moogt.get_proposition())

        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       invitee=moogt_invitee_2, inviter=moogt.get_proposition())

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_retrieve_no_recently_invited(self):
        """
        test successfully retrieve no recently invited users
        """

        user = create_user_and_login(self)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_distinct_users(self):
        """
        test successfully retrieve one recently invited user even if the user has
        been invited twice
        """

        user = create_user_and_login(self)
        moogt_invitee = create_user("invitee", "password")

        moogt = create_moogt_with_user(user, resolution="test resolution")

        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       invitee=moogt_invitee, inviter=moogt.get_proposition())

        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       invitee=moogt_invitee, inviter=moogt.get_proposition())

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)


class PendingInvitationListAPIViewTests(APITestCase):
    def get(self, type):
        url = reverse('api:invitations:list_invitation', kwargs={
                      'version': 'v1'}) + '?type=' + type
        return self.client.get(url)

    def test_list_sent_invitation(self):
        """
        test if received invitations exist it should return them
        """
        moogt_invitee = create_user("invitee", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")

        invitation = create_invitation(moogt, InvitationStatus.PENDING.name,
                                       invitee=moogt_invitee, inviter=moogt.get_proposition())

        response = self.get(InvitationType.SENT.name)

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_received_invitation(self):
        """
        test if sent invitations exist it should return them
        """
        moogt_inviter = create_user("inviter", "password")
        moogt = create_moogt_with_user(
            moogt_inviter, resolution="test resolution")

        user = create_user_and_login(self)

        invitation = create_invitation(moogt, InvitationStatus.PENDING.name,
                                       invitee=user, inviter=moogt.get_proposition())

        response = self.get(InvitationType.RECEIVED.name)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_no_sent_invitaions(self):
        """
        test if no sent invitations exist it should return an empty list
        """
        user = create_user_and_login(self)
        response = self.get(InvitationType.SENT.name)

        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_no_received_invitations(self):
        """
        test if no received invitations exist it should return an empty list
        """
        user = create_user_and_login(self)
        response = self.get(InvitationType.RECEIVED.name)

        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_one_sent_one_received_invitations_exist(self):
        """
        test if one invitation is received and one is sent it should return the one queried for
        """
        user_1 = create_user("test_user", "password")
        moogt = create_moogt_with_user(
            user_1, resolution="test resolution", create_invitation=False)

        user_2 = create_user_and_login(self)
        moogt_2 = create_moogt_with_user(
            user_2, resolution="test resolution", create_invitation=False)

        invitation = create_invitation(moogt, InvitationStatus.PENDING.name,
                                       invitee=user_1, inviter=moogt.get_proposition())

        invitation_2 = create_invitation(moogt_2, InvitationStatus.PENDING.name,
                                         invitee=user_2, inviter=moogt.get_proposition())

        response = self.get(InvitationType.RECEIVED.name)

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_pending_sent_invitations_exist(self):
        """
        test non pending invitations should not show up in the response
        """
        moogt_invitee = create_user("invitee", "password")

        user = create_user_and_login(self)
        moogt = create_moogt_with_user(user, resolution="test resolution")

        invitation = create_invitation(moogt, InvitationStatus.ACCEPTED.name,
                                       invitee=moogt_invitee, inviter=moogt.get_proposition())

        response = self.get(InvitationType.SENT.name)
        # self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_pending_received_invitation_exist(self):
        """
        test if sent invitations exist it should return them
        """
        moogt_inviter = create_user("inviter", "password")
        moogt = create_moogt_with_user(
            moogt_inviter, resolution="test resolution")

        user = create_user_and_login(self)

        invitation = create_invitation(moogt, InvitationStatus.CANCELLED.name,
                                       invitee=user, inviter=moogt_inviter)

        response = self.get(InvitationType.RECEIVED.name)

        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pending_receieved_invitation_list_ordering(self):
        """
        test if the first on the invitation list is the latest invitation list
        """
        user_1 = create_user("test_user", "password")

        moogt = create_moogt_with_user(user_1, resolution="test resolution")
        moogt_2 = create_moogt_with_user(user_1, resolution="test resolution")

        user_2 = create_user_and_login(self)

        invitation = create_invitation(moogt, InvitationStatus.PENDING.name,
                                       invitee=user_2, inviter=moogt.get_proposition())
        invitation2 = create_invitation(moogt_2, InvitationStatus.PENDING.name,
                                        invitee=user_2, inviter=moogt.get_proposition())
        response = self.get(InvitationType.RECEIVED.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], invitation2.id)

    def test_pending_receieved_invitation_list_ordering(self):
        """
        test if the first on the invitation list is the latest invitation list
        """
        user_1 = create_user("test_user", "password")

        user_2 = create_user_and_login(self)

        moogt = create_moogt_with_user(user_2, resolution="test resolution")
        moogt_2 = create_moogt_with_user(user_2, resolution="test resolution")

        invitation = create_invitation(moogt, InvitationStatus.PENDING.name,
                                       invitee=user_1, inviter=moogt.get_proposition())
        invitation2 = create_invitation(moogt_2, InvitationStatus.PENDING.name,
                                        invitee=user_1, inviter=moogt.get_proposition())
        response = self.get(InvitationType.SENT.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], invitation2.id)


class InviteMoogterViewTests(APITestCase):
    def post(self, data):
        url = reverse('api:invitations:invite_moogter',
                      kwargs={'version': 'v1'})
        return self.client.post(url, data=data)

    def assert_invitation_exists(self, invitee, inviter, moogt, expected):
        invitation_exists = Invitation.objects \
            .filter(moogt_id=moogt.id, invitee_id=invitee.id, inviter_id=inviter.id) \
            .exists()
        self.assertEqual(invitation_exists, expected)

    def test_user_not_authenticatedI(self):
        """
        If the user is not authenticated, it should response with not-authorized response code
        """
        response = self.post({})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_with_none_existing_moogt(self):
        """
        If the moogt_id given in the request body does not exist, it should respond with a
        not found response
        """
        create_user_and_login(self)
        invitee = create_user('invitee_user', 'testpassword')
        response = self.post({'moogt_id': 404, 'invitee_id': invitee.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_none_existing_invitee_id(self):
        """
        If the invitee with the given id does not exist, it should respond with a
        not found response
        """
        create_user_and_login(self)
        moogt = create_moogt()
        response = self.post({'moogt_id': moogt.id, 'invitee_id': 404})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_valid_request(self):
        """
        If the request is valid, it should create an invitation
        """
        inviter = create_user_and_login(self)
        invitee = create_user('invitee_user', 'testpassword')
        moogt = create_moogt()
        moogt.set_proposition(inviter)
        moogt.save()

        response = self.post({'moogt_id': moogt.id, 'invitee_id': invitee.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_invitation_exists(invitee, inviter, moogt, True)

    def test_inviter_and_invitee_are_same(self):
        """
        If the inviter and invitee anre the same, it should not create invitation
        """
        user = create_user_and_login(self)
        moogt = create_moogt()
        moogt.set_proposition(user)
        moogt.save()

        response = self.post({'moogt_id': moogt.id, 'invitee_id': user.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_invitation_exists(user, user, moogt, False)

    def test_inviter_is_not_proposition(self):
        """
        If the inviter is not the proposition, it should not create an invitation
        Removed since the inviter can now be a proposition
        """
        # inviter = create_user_and_login(self)
        # moogt = create_moogt()

        # invitee = create_user('invitee_user', 'testpassword')
        # response = self.post({'moogt_id': moogt.id, 'invitee_id': invitee.id})
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assert_invitation_exists(
        #     inviter=inviter, invitee=invitee, moogt=moogt, expected=False)

    def test_with_already_existing_opposition(self):
        """
        If an opposition already exists for the moogt, it should not create an invitation
        Removed Because we now need to send two invites if user creates moogt as moderator
        """
        # inviter = create_user_and_login(self)
        # moogt = create_moogt(opposition=True)
        # moogt.set_proposition(inviter)
        # moogt.save()

        # invitee = create_user('invitee_user', 'testpassword')
        # response = self.post({'moogt_id': moogt.id, 'invitee_id': invitee.id})
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assert_invitation_exists(
        #     inviter=inviter, invitee=invitee, moogt=moogt, expected=False)

    def test_with_already_pending_or_accepted_existing_invitation(self):
        """
        If a pending or accepted invitation exists, it should not create an invitation
        Removed Because we now need to send two invites if user creates moogt as moderator
        """
        # inviter = create_user_and_login(self)
        # moogt = create_moogt()
        # moogt.set_proposition(inviter)
        # moogt.save()

        # invitee = create_user('invitee_user', 'testpassword')
        # invitee_2 = create_user('invitee_user2', 'testpassword')
        # invitation = Invitation(
        #     moogt=moogt, invitee=invitee_2, inviter=inviter)
        # invitation.set_status(InvitationStatus.pending())
        # invitation.save()

        # response = self.post({'moogt_id': moogt.id, 'invitee_id': invitee.id})
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assert_invitation_exists(
        #     inviter=inviter, invitee=invitee, moogt=moogt, expected=False)

        # Invitation.objects.all().delete()
        # invitation = Invitation(
        #     moogt=moogt, invitee=invitee_2, inviter=inviter)
        # invitation.status = InvitationStatus.accepted()
        # invitation.save()

        # response = self.post({'moogt_id': moogt.id, 'invitee_id': invitee.id})
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assert_invitation_exists(
        #     inviter=inviter, invitee=invitee, moogt=moogt, expected=False)

    def test_send_notifications(self):
        """
        If the request is valid, it sends notification
        """
        inviter = create_user_and_login(self)
        invitee = create_user('invitee_user', 'testpassword')
        moogt = create_moogt()
        moogt.set_proposition(inviter)
        moogt.save()

        self.post({'moogt_id': moogt.id, 'invitee_id': invitee.id})

        invitee = MoogtMedaUser.objects.get(id=invitee.id)
        self.assertGreater(invitee.notifications.count(), 0)
        self.assertEqual(invitee.notifications.first().recipient, invitee)
        self.assertEqual(invitee.notifications.first().target,
                         Invitation.objects.first())


class UpdateInvitationViewTests(APITestCase):
    @staticmethod
    def create_invitation(moogt, invitation_status, invitee=None, inviter=None):
        invitation = Invitation(
            moogt=moogt, status=invitation_status, invitee=invitee, inviter=inviter)
        invitation.save()

        return invitation

    def post(self, invitation_id, body):
        url = reverse('api:invitations:update_invitation', kwargs={
                      'pk': invitation_id, 'version': 'v1'})
        return self.client.post(url, body)

    def test_user_is_not_authenticated(self):
        """
        If user is not authenticated, it should not set user as opposition
        """
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.pending())
        response = self.post(invitation.id, {'action': 'test action'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_none_existing_invitation(self):
        """
        If the request contains a none existing invitation, it should respond with a 404 response
        """
        create_user_and_login(self)
        response = self.post(404, {'action': 'test action'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_none_pending_invitation(self):
        """
        If the invitation is not a pending state, it should respond with bad request
        """
        create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.accepted())

        response = self.post(invitation.id, {'action': 'test action'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_invalid_action(self):
        """
        If the request contains an invalid action, it should respond with a not found response
        """
        create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.pending())

        response = self.post(invitation.id, {'action': 'invalid action'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_decline_action(self):
        """
        If the request contains an action set to decline, it should se the status appropriately
        """
        user = create_user_and_login(self)
        moogt = create_moogt()
        inviter = create_user('inviter', 'pass123')
        invitation = self.create_invitation(
            moogt, InvitationStatus.pending(), invitee=user, inviter=inviter)
        response = self.post(invitation.id, {'action': 'decline'})

        invitation_content_type = ContentType.objects.get_for_model(Invitation)
        notifications = Notification.objects \
            .filter(target_content_type=invitation_content_type,
                    target_object_id=invitation.id)

        invitation = Invitation.objects.get(id=invitation.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(invitation.status, InvitationStatus.declined())
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first(
        ).data['data']['invitation']['status'], InvitationStatus.DECLINED.name)
        self.assertEqual(invitation.message.summaries.filter(
            verb=MessageSummary.VERBS.DECLINE.value).count(), 1)

    def test_with_decline_action_but_updater_is_not_invitee(self):
        """
        If the updater is not the invitee, it should not update the Invitation.
        """
        create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.pending())
        response = self.post(invitation.id, {'action': 'decline'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invitation = Invitation.objects.get(id=invitation.id)
        self.assertEqual(invitation.status, InvitationStatus.pending())

    def test_with_accept_action(self):
        """
        If the request contains an accept as action, it should update the invitation properly
        """
        user = create_user_and_login(self)
        invitee = create_user('invitee', 'pass123')
        moogt = create_moogt()
        invitation = self.create_invitation(
            moogt, InvitationStatus.pending(), invitee=user, inviter=invitee)

        response = self.post(invitation.id, {'action': 'accept'})

        self.assertEqual(response.status_code, 200)
        invitation = Invitation.objects.get(pk=invitation.id)
        self.assertEqual(invitation.status, InvitationStatus.accepted())
        self.assertEqual(invitation.message.summaries.count(), 2)
        self.assertEqual(invitation.message.summaries.filter(
            verb=MessageSummary.VERBS.ACCEPT.value).count(), 1)

    def test_with_accept_action_where_updater_is_not_invitee(self):
        """
        If the request contains an accept action but the updater is not the invitee, it should not update the invitation
        """
        create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.pending())

        response = self.post(invitation.id, {'action': 'accept'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invitation = Invitation.objects.get(pk=invitation.id)
        self.assertEqual(invitation.status, InvitationStatus.pending())
        self.assertIsNone(invitation.moogt.get_opposition())

    def test_with_cancel_action(self):
        """
        If the request contains the action cancel, it should update the Invitation properly
        """
        user = create_user_and_login(self)
        moogt = create_moogt()
        invitee = create_user('invitee', 'pass')
        invitation = self.create_invitation(
            moogt, InvitationStatus.pending(), inviter=user, invitee=invitee)

        response = self.post(invitation.id, {'action': 'cancel'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation = Invitation.objects.get(pk=invitation.id)

        invitation_content_type = ContentType.objects.get_for_model(Invitation)
        notifications = Notification.objects \
            .filter(target_content_type=invitation_content_type,
                    target_object_id=invitation.id)

        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first(
        ).data['data']['invitation']['status'], InvitationStatus.CANCELLED.name)

        self.assertEqual(invitation.status, InvitationStatus.cancelled())
        self.assertIsNone(invitation.moogt.get_opposition())
        self.assertEqual(invitation.message.summaries.filter(verb=MessageSummary.VERBS.CANCEL.value,
                                                             actor=user).count(), 1)

    def test_with_cancel_action_where_updater_is_not_the_inviter(self):
        """
        If the request contains the action cancel and the updater is not the inviter, it should not update the invitation
        """
        create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.pending())

        response = self.post(invitation.id, {'action': 'cancel'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invitation = Invitation.objects.get(pk=invitation.id)
        self.assertEqual(invitation.status, InvitationStatus.pending())

    def test_with_back_action_for_an_accepted_invitation(self):
        """
        If a back action is requested for an accepted invitation,
        it should go back to it's previous pending state.
        """
        user = create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.accepted())
        invitation.set_inviter(user)
        invitation.save()

        response = self.post(invitation.id, {'action': 'back'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertEqual(invitation.get_status(), InvitationStatus.pending())

    def test_with_back_action_for_a_revised_invitation(self):
        """
        If a back action is requested for a revised invitation,
        it should go back to it's previous pending state.
        """
        user = create_user_and_login(self)
        moogt = create_moogt()
        invitation = self.create_invitation(moogt, InvitationStatus.revised())
        invitation.set_inviter(user)
        invitation.save()

        response = self.post(invitation.id, {'action': 'back'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertEqual(invitation.get_status(), InvitationStatus.pending())


class StartInvitationViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        invitee = create_user('invitee', 'pass123')
        self.moogt = create_moogt()
        self.moogt.set_proposition(self.user)
        self.moogt.save()
        self.invitation = create_invitation(
            self.moogt, InvitationStatus.accepted(), inviter=self.user, invitee=invitee)

    def post(self, pk, body):
        url = reverse('api:invitations:start_invitation',
                      kwargs={'pk': pk, 'version': 'v1'})
        return self.client.post(url, body)

    def test_moogt_invitation_with_pending_invitation(self):
        """If there exists pending suggestions, it should not start."""
        self.invitation.set_status(InvitationStatus.revised())
        self.invitation.save()
        self.moogt.mini_suggestions.create()
        response = self.post(self.invitation.id, {'action': 'now'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_the_moogt_invitation(self):
        """If the moogt is started it's status should be updated."""
        self.invitation.set_status(InvitationStatus.accepted())
        self.invitation.save()
        response = self.post(self.invitation.id, {'action': 'now'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.get_status(),
                         InvitationStatus.started())
        self.assertFalse(self.invitation.moogt.func_has_started())
        # might not always be the case if for example moderator invites
        # self.assertEqual(self.invitation.moogt.get_opposition(),
        #                  self.invitation.get_invitee())
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertEqual(self.user.notifications.first().verb, 'have started')

    def test_start_the_moogt_without_moogter(self):
        """If the moogt has no moogter, it should not start."""
        user1 = create_user_and_login(self, 'user1', 'pass123')
        user2 = create_user('user2', 'pass123')
        user3 = create_user('user3', 'pass123')
        self.invitation.set_status(InvitationStatus.accepted())
        self.invitation.save()
        self.invitation.moogt.set_proposition(user2)
        self.invitation.moogt.set_proposition(user3)
        self.invitation.moogt.save()
        response = self.post(self.invitation.id, {'action': 'now'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EditInvitationViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.invitee = create_user('invitee', 'pass123')
        self.moogt = create_moogt('resolution')
        self.invitation = create_invitation(inviter=self.user,
                                            invitee=self.invitee,
                                            moogt=self.moogt)

    def post(self, invitation_id, body):
        url = reverse('api:invitations:edit_invitation', kwargs={
                      'pk': invitation_id, 'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_non_authenticated_user(self):
        """
        A non-authenticated user should be dealt with a non-authorized user.
        """
        self.client.logout()
        response = self.post(self.invitation.id, None)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_existing_invitation_id(self):
        """
        A non existing invitation should be dealt with a not found response.
        """
        response = self.post(404, None)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_inviter(self):
        """
        A non inviter cannot edit an invitation.
        """
        create_user_and_login(self, 'test_user', 'pass123')
        response = self.post(self.invitation.id, None)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sets_invitation_status_to_edited(self):
        """
        An invitation must set to edited and a new invitation in the pending state must be created.
        """
        invitation_id = self.invitation.id
        response = self.post(self.invitation.id, {
            'resolution': 'new resolution',
            'description': None
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        invitation = Invitation.objects.get(pk=invitation_id)
        self.assertEqual(invitation.get_status(), InvitationStatus.edited())
        self.assertEqual(Invitation.objects.count(), 2)
        self.assertEqual(invitation.message.summaries.filter(
            verb=MessageSummary.VERBS.EDIT.value).count(), 1)

    def test_creates_an_invitation_message_when_edited(self):
        """
        An InvitationMessage object must be created when the invitation is edited.
        """
        invitation_id = self.invitation.id
        self.assertEqual(InvitationMessage.objects.count(), 1)
        self.post(self.invitation.id, {
            'resolution': 'new resolution',
            'description': None
        })
        self.assertEqual(InvitationMessage.objects.count(), 2)
        invitation = Invitation.objects.get(pk=invitation_id)
        self.assertIsNotNone(invitation.child_invitation)
        self.assertIsNotNone(invitation.child_invitation.message)
        self.assertEqual(
            invitation.child_invitation.message.summaries.count(), 1)

    def test_updates_the_moogt_with_new_changes(self):
        """
        Updates the already existing moogt with the new changes from the client.
        """
        self.assertEqual(self.moogt.get_resolution(), 'resolution')
        response = self.post(self.invitation.id, {
            'resolution': 'new resolution',
            'description': None
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.moogt.refresh_from_db()
        self.invitation.refresh_from_db()
        self.assertEqual(self.moogt.get_resolution(), 'resolution')
        self.assertEqual(
            self.invitation.get_moogt().get_resolution(), 'resolution')
        self.assertEqual(self.invitation.child_invitation.get_moogt(
        ).get_resolution(), 'new resolution')
        self.assertEqual(Moogt.objects.count(), 2)

    def test_invalid_field_provided_in_the_request_body(self):
        """
        An invalid request body should be dealt with a bad request response.
        """
        response = self.post(self.invitation.id, {
            'invalid_resolution': 'new resolution',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_the_moogt_invitation_with_banner_image(self):
        """
        Updates the already existing moogt with banner image update from the client
        """
        self.assertEqual(self.moogt.get_resolution(), 'resolution')

        banner: MoogtBanner = MoogtBanner.objects.create()
        response = self.post(self.invitation.id, {
            'banner': banner.id
        })

        self.invitation.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.invitation.child_invitation.get_moogt().banner.id, banner.id)


class ModeratorInvitationViewTest(APITestCase):
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        participant_user = create_user(
            username='participant_user', password='testpassword')
        self.invitee = create_user('CCC', 'pass123')
        self.moogt = create_moogt('resolution')
        self.moderator = create_user('moderator', 'pass123')
        self.invitation = create_invitation(inviter=self.user,
                                            invitee=self.invitee,
                                            moogt=self.moogt)

        self.conversation = Conversation.objects.create()
        self.conversation.add_participant(
            user=participant_user, role=Participant.ROLES.MOOGTER.value)

    def post(self, invitation_id, body):
        url = reverse('api:invitations:moderator_invitation_action', kwargs={
            'pk': invitation_id, 'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_accept_moderator_invitation(self):
        """Tests accpet action of the moderator invitation """

        mod_invitation = ModeratorInvitation.objects.create(
            status=ModeratorInvititaionStatus.pending(), moderator=self.moderator, invitation=self.invitation)

        response = self.post(mod_invitation.id, {'action': 'accept'})

        invitation_content_type = ContentType.objects.get_for_model(
            ModeratorInvitation)
        notifications = Notification.objects \
            .filter(target_content_type=invitation_content_type,
                    target_object_id=mod_invitation.id)

        self.moogt.refresh_from_db()

        self.assertIsNotNone(self.moogt.get_moderator())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'],
                         ModeratorInvititaionStatus.accepted())

        self.assertEqual(notifications.count(), 3)
        self.assertEqual(mod_invitation.moderator_message.summaries.count(), 2)
        self.assertEqual(mod_invitation.moderator_message.summaries.filter(
            verb=MessageSummary.VERBS.ACCEPT.value).count(), 1)

    def test_decline_moderator_invitation(self):
        """Tests decline action of the moderator invitation """
        mod_invitation = ModeratorInvitation.objects.create(
            status=ModeratorInvititaionStatus.pending(), moderator=self.moderator, invitation=self.invitation)

        response = self.post(mod_invitation.id, {'action': 'decline'})
        invitation_content_type = ContentType.objects.get_for_model(
            ModeratorInvitation)
        notifications = Notification.objects \
            .filter(target_content_type=invitation_content_type,
                    target_object_id=mod_invitation.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'],
                         ModeratorInvititaionStatus.declined())

        self.assertEqual(notifications.count(), 3)
        self.assertEqual(mod_invitation.moderator_message.summaries.count(), 2)
        self.assertEqual(mod_invitation.moderator_message.summaries.filter(
            verb=MessageSummary.VERBS.DECLINE.value).count(), 1)

    def test_cancel_moderator_invitation(self):
        """Tests cancel an action of the moderator invitation """
        mod_invitation = ModeratorInvitation.objects.create(
            status=ModeratorInvititaionStatus.pending(), moderator=self.moderator, invitation=self.invitation)

        response = self.post(mod_invitation.id, {'action': 'cancel'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'],
                         ModeratorInvititaionStatus.cancelled())

        self.assertEqual(mod_invitation.moderator_message.summaries.count(), 2)
        self.assertEqual(mod_invitation.moderator_message.summaries.filter(
            verb=MessageSummary.VERBS.CANCEL.value).count(), 1)
