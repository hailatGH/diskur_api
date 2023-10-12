from django.forms import ValidationError
from django.test import TestCase
from django.urls import reverse
from django_comments.forms import CommentForm
from meda.tests.test_models import create_moogt

from users.models import Activity, ActivityType, Blocking, Profile, MoogtMedaUser
from users.models import CreditPoint


# Create your tests here.
class ProfileModelTests(TestCase):
    @staticmethod
    def create_user():
        user = MoogtMedaUser(username='test_user')
        user.set_password('testpassword')
        user.save()

        profile = Profile()
        profile.user = user
        profile.save()

        return user

    def test_credit_pts_count_with_a_credit_point_with_view_proposition_moogt_type(self):
        """
        The count for the view_proposition_moogt type should be 1
        """
        user = self.create_user()
        CreditPoint(profile=user.profile, type=ActivityType.view_proposition_moogt.name).save()

        credit_pts_count = user.profile.credit_pts_count()
        self.assertEqual(credit_pts_count[0]['type__count'], 1)

    def test_credit_pts_count_with_a_credit_point_with_view_opposition_moogt_type(self):
        """
        The count for the view_opposition_moogt type should be 1
        """
        user = self.create_user()
        CreditPoint(profile=user.profile, type=ActivityType.view_opposition_moogt.name).save()
        credit_pts_count = user.profile.credit_pts_count()
        self.assertEqual(credit_pts_count[0]['type__count'], 1)

    def test_credit_pts_count_with_a_credit_point_with_make_comment_type(self):
        """
        The count for the make_comment_type type should be 1
        """
        user = self.create_user()
        CreditPoint(profile=user.profile, type=ActivityType.make_comment.name).save()
        credit_pts_count = user.profile.credit_pts_count()
        self.assertEqual(credit_pts_count[0]['type__count'], 1)

    def test_credit_pts_count_with_a_couple_of_credit_points(self):
        """
        The count for each type should be calculated correctly.
        """
        user = self.create_user()
        CreditPoint(profile=user.profile, type=ActivityType.view_proposition_moogt.name).save()
        CreditPoint(profile=user.profile, type=ActivityType.view_proposition_moogt.name).save()
        CreditPoint(profile=user.profile, type=ActivityType.view_proposition_moogt.name).save()
        CreditPoint(profile=user.profile, type=ActivityType.view_opposition_moogt.name).save()
        CreditPoint(profile=user.profile, type=ActivityType.make_comment.name).save()

        credit_pts_count = user.profile.credit_pts_count()
        for type_count in credit_pts_count:
            if type_count['type'] == 'view_proposition_moogt':
                self.assertEqual(type_count['type__count'], 3)
            elif type_count['type'] == 'view_opposition_moogt':
                self.assertEqual(type_count['type__count'], 1)
            elif type_count['type'] == 'make_comment':
                self.assertEqual(type_count['type__count'], 1)


def create_activity(activity_type, object_id):

    user = MoogtMedaUser(username="username")
    user.set_password("password")
    user.save()

    profile = Profile()
    profile.user = user
    profile.save()

    activity = Activity.record_activity(profile, activity_type, object_id)

    return activity


def create_user(username, password):
    user = MoogtMedaUser(username=username)
    user.set_password(password)
    user.first_name="Firstname"
    user.email="user@email.com"
    user.save()

    profile = Profile()
    profile.user = user
    profile.save()
    user.profile = profile

    return user


class ActivityModelTests(TestCase):

    def test_func_upvote_argument(self):
        """
        record_activity function registers upvote activity in the database
        """
        activity = create_activity(ActivityType.upvote_argument.name, 1)

        self.assertEqual(Activity.objects.all().count(), 1)
        self.assertEqual(activity.type, ActivityType.upvote_argument.name)
        self.assertEqual(activity.object_id, 1)

    def test_func_downvote_argument(self):
        """
        record_activity function registers downvote activity in the database
        """
        activity = create_activity(ActivityType.downvote_argument.name, 1)

        self.assertEqual(Activity.objects.all().count(), 1)
        self.assertEqual(activity.type, ActivityType.downvote_argument.name)
        self.assertEqual(activity.object_id, 1)

    def test_func_make_comment(self):
        """
        record_activity function registers make_comment activity in the database
        """
        activity = create_activity(ActivityType.make_comment.name, 1)

        self.assertEqual(Activity.objects.all().count(), 1)
        self.assertEqual(activity.type, ActivityType.make_comment.name)
        self.assertEqual(activity.object_id, 1)

    def test_func_create_moogt(self):
        """
        record_activity function registers create moogt activity in the database
        """
        activity = create_activity(ActivityType.create_moogt.name, 1)

        self.assertEqual(Activity.objects.all().count(), 1)
        self.assertEqual(activity.type, ActivityType.create_moogt.name)
        self.assertEqual(activity.object_id, 1)

    def test_func_create_argument(self):
        """
        record_activity function registers create argument activity in the database
        """
        activity = create_activity(ActivityType.create_argument.name, 1)

        self.assertEqual(Activity.objects.all().count(), 1)
        self.assertEqual(activity.type, ActivityType.create_argument.name)
        self.assertEqual(activity.object_id, 1)

    def test_comment_was_posted_signal_records_activity(self):
        """
        recognize comment_was_posted signal and register make comment activity in the database
        """
        user = create_user("username", "password")

        moogt = create_moogt(has_opening_argument=True)
        args = moogt.arguments.first()

        my_form = CommentForm(args)
        security_dict = my_form.generate_security_data()
        comment_detail_dict = {"comment": "comment",
                        "name": user.first_name,
                        "email": user.email,
                        "reply_to": 0}

        url = reverse('comments-post-comment')
        self.client.login(username="username", password="password")
        response = self.client.post(url, {**comment_detail_dict, **security_dict})

        self.assertEqual(Activity.objects.all().count(), 1)
        activity = Activity.objects.first()
        self.assertEqual(activity.type, ActivityType.make_comment.name)

class BlockingModelTests(TestCase):
    def test_clean_validates_model_properly(self):
        """
        The clean method should validate properly.
        """
        user_1 = create_user('user1', 'pass123')
        blocking = Blocking(user=user_1, blocked_user=user_1)
        self.assertRaises(ValidationError, blocking.full_clean)