import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APITestCase

from api.enums import Visibility, ReactionType, ViewType
from api.tests.utility import create_user, create_view, create_comment, create_argument
from meda.models import Score


class ViewModelTests(APITestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = create_user('test_user', 'test_password')

    def test_comments_count_no_comment_exists(self):
        """
        If no comments exists, it should return 0 as the count
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        self.assertEqual(view.comments_count(), 0)

    def test_comments_count_one_comment_exists(self):
        """
        This function should return the number of comments for a given view
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        create_comment(view, self.user, 'test comment')
        view.refresh_from_db()
        self.assertEqual(view.comments_count(), 1)

    def test_a_view_that_has_no_parent(self):
        """
        The parent property should return None if the view has no parent.
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        self.assertIsNone(view.parent)

    def test_parent_property_returns_parent_view(self):
        """
        The parent property returns the parent_view if it's the parent of the view.
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        parent_view = create_view(self.user, 'test parent content')
        view.parent_view = parent_view
        view.save()
        self.assertEqual(view.parent, parent_view)

    def test_parent_property_return_parent_argument(self):
        """
        The parent property must return the argument if it's the parent of the view.
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        argument = create_argument(create_user('opposition_user', 'test_password'), 'test argument')
        view.parent_argument = argument
        view.save()
        self.assertEqual(view.parent, argument)

    def test_parent_property_raises_exception(self):
        """
        The parent property can't point to both argument and view at the same time. If that's the case
        an exception must be raised.
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        argument = create_argument(create_user('opposition_user', 'test_password'), 'test argument')
        parent_view = create_view(self.user, 'test parent content')
        view.parent_view = parent_view
        view.parent_argument = argument
        view.save()
        self.assertRaises(ValidationError, getattr, view, 'parent')

    def test_check_is_content_creator(self):
        """
        This tests whether the function check_is_content_creator properly validates if
        a user is the creator of a content
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        user = create_user("username", "password")
        self.assertEqual(view.check_is_content_creator(self.user), True)
        self.assertEqual(view.check_is_content_creator(user), False)

    def test_reaction_count_of_type(self):
        """
        Returns zero if there are no reactions for a view.
        """
        view = create_view(self.user, 'test content')
        self.assertEqual(view.reactions_count_of_type(ReactionType.ENDORSE.name), 0)
        self.assertEqual(view.reactions_count_of_type(ReactionType.DISAGREE.name), 0)

    def test_reaction_count_of_type_endorse_counts_properly(self):
        """
        If there is a reaction of type endorse, it should be counted properly.
        """
        view = create_view(self.user, 'test content')
        reaction_view = create_view(self.user, 'reaction view')
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.parent_view = view
        reaction_view.save()

        self.assertEqual(view.reactions_count_of_type(ReactionType.ENDORSE.name), 1)

    def test_reaction_count_of_type_disagree_counts_properly(self):
        """
        If there is a reaction of type disagree, it should be counted properly.
        """
        view = create_view(self.user, 'test content')
        reaction_view = create_view(self.user, 'reaction view')
        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.parent_view = view
        reaction_view.save()

        self.assertEqual(view.reactions_count_of_type(ReactionType.DISAGREE.name), 1)


class ViewScoreModelTests(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = create_user('test_user', 'test_password')

    def test_can_score_be_updated(self):
        """
        This method should return true if now - score_last_update_at is greater than X,
        where X is a duration we can control
        """
        view = create_view(self.user, 'test content', Visibility.PUBLIC.name)
        self.assertFalse(view.score._can_score_be_updated())

        view.score.score_last_updated_at = timezone.now() - datetime.timedelta(hours=Score.TRENDING_DURATION_HOURS)
        view.score.save()

        self.assertTrue(view.score._can_score_be_updated())
