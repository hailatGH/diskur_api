from unittest import mock

from django.db.models.signals import post_save
from django.test import TestCase

from api.tests.utility import catch_signal
from invitations.models import Invitation
from meda.tests.test_models import create_moogt


class InvitationModelTests(TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.moogt = create_moogt()
        self.invitation = Invitation(moogt=self.moogt)

    def test_should_send_post_save_signal_if_an_invitation_is_saved(self):
        """
        If a new invitation is saved, it should send a post_save signal.
        """

        with catch_signal(post_save) as handler:
            self.invitation.save()

        handler.assert_called_once_with(
            sender=mock.ANY,
            instance=self.invitation,
            created=True,
            update_fields=mock.ANY,
            raw=mock.ANY,
            using=mock.ANY,
            signal=post_save
        )
