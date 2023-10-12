from django.test import TestCase

from api.tests.utility import create_user, create_user_and_login
from users.tests.factories import BlockingFactory
from views.models import View
from views.tests.factories import ViewFactory


class ViewQuerySetTests(TestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.view = ViewFactory(user=self.user)

        self.reactions = ViewFactory.create_batch(3, parent_view=self.view)

    def test_get_views_includes_fields_for_reactions(self):
        """Should include the top reaction for the view."""
        result = View.objects.get_feed_views(self.user).first()
        self.assertTrue(hasattr(result, 'top_reaction_content'))
        self.assertTrue(hasattr(result, 'top_reaction_user_id'))
        self.assertTrue(hasattr(result, 'top_reaction_reaction_type'))
        self.assertTrue(hasattr(result, 'my_top_reaction_content'))
        self.assertTrue(hasattr(result, 'my_top_reaction_user_id'))
        self.assertTrue(hasattr(result, 'my_top_reaction_reaction_type'))

    def test_gets_top_reaction_for_a_view(self):
        """Should get a single top reaction."""
        top_reaction: View = self.reactions[1]
        top_reaction.score.overall_score = 10
        top_reaction.score.save()

        result = View.objects.get_feed_views(self.user).first()
        self.assertEqual(result.top_reaction_content, top_reaction.content)
        self.assertEqual(result.top_reaction_user_id, top_reaction.user_id)

    def test_gets_top_own_reaction_for_a_view(self):
        """Should get a single top reaction made by the user."""
        own_reactions = ViewFactory.create_batch(3, parent_view=self.view, user=self.user)

        top_reaction: View = own_reactions[0]
        top_reaction.score.overall_score = 10
        top_reaction.score.save()

        result = View.objects.get_feed_views(self.user).get(id=self.view.id)

        self.assertNotEqual(result.top_reaction_content, top_reaction.content)
        self.assertNotEqual(result.top_reaction_user_id, top_reaction.user_id)

        self.assertEqual(result.my_top_reaction_content, top_reaction.content)
        self.assertEqual(result.my_top_reaction_user_id, top_reaction.user_id)

    def test_get_feed_views_should_include_has_more_reactions_field(self):
        """
        Should have a has_more_reactions field for indicating whether or not the view has more reactions
        beside the my_top_reaction and top_reaction.
        """
        self.reactions = ViewFactory.create_batch(3, parent_view=self.view, content=None)
        result = View.objects.get_feed_views(self.user).first()
        self.assertTrue(hasattr(result, 'total_reactions'))
        self.assertEqual(result.total_reactions, 3)
        
    def test_filter_views_by_blocked_users_should_filter_views_that_are_created_by_someone_you_have_blocked(self):
        """Should filter views that are created by users that you're blocking.
        """
        View.objects.all().delete()
        
        user1 = create_user('testuser1', 'pass123')
        user2 = create_user('testuser2', 'pass123')
        
        BlockingFactory.create(user=self.user, blocked_user=user2)
        
        self.view1 = ViewFactory.create(user=user1)
        self.view2 = ViewFactory.create(user=user2)
        
        result = View.objects.filter_views_by_blocked_users(self.user)
        self.assertEqual(result.count(), 1)
        
    def test_filter_views_by_blocked_users(self):
        """
        Should filter content created by users that have blocked you.
        """
        View.objects.all().delete()
        
        user1 = create_user('testuser1', 'pass123')
        user2 = create_user('testuser2', 'pass123')
        
        BlockingFactory.create(user=self.user, blocked_user=user2)
        
        self.view1 = ViewFactory.create(user=self.user)
        self.view2 = ViewFactory.create(user=user2)
        
        result = View.objects.filter_views_by_blocked_users(user2)
        self.assertEqual(result.count(), 1)
        
