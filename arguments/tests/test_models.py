from django.test import TestCase

from api.enums import ReactionType
from api.tests.utility import create_argument, create_user, create_view
from arguments.enums import ArgumentReactionType


class ArgumentModelTests(TestCase):

    def setUp(self) -> None:
        self.user = create_user('mgtr_user', 'pass123')
        self.argument = create_argument(argument='argument', user=self.user)
        self.reaction_view = create_view(user=self.user)
        self.reaction_view.parent_argument = self.argument

    def test_reaction_count_of_type_endorse(self):
        """Should count the endorsement count of an argument."""
        self.reaction_view.reaction_type = ReactionType.ENDORSE.name
        self.reaction_view.save()
        result = self.argument.reactions_count_of_type(ReactionType.ENDORSE.name)
        self.assertEqual(result, 1)
        result = self.argument.reactions_count_of_type(ReactionType.DISAGREE.name)
        self.assertEqual(result, 0)

    def test_reaction_count_of_type_type_disagree(self):
        """Should count the disagreement count of an argument."""
        self.reaction_view.reaction_type = ReactionType.DISAGREE.name
        self.reaction_view.save()
        result = self.argument.reactions_count_of_type(ReactionType.DISAGREE.name)
        self.assertEqual(result, 1)
        result = self.argument.reactions_count_of_type(ReactionType.ENDORSE.name)
        self.assertEqual(result, 0)

    def test_should_count_reactions_by_moogters(self):
        """Should count the reactions by moogters."""
        self.reaction_view.delete()
        reaction_argument = create_argument(argument='reaction argument', user=self.user)
        reaction_argument.react_to = self.argument
        reaction_argument.reaction_type = ArgumentReactionType.ENDORSEMENT.name
        reaction_argument.save()

        result = self.argument.reactions_count_of_type(ReactionType.DISAGREE.name)
        self.assertEqual(result, 0)
        result = self.argument.reactions_count_of_type(ReactionType.ENDORSE.name)
        self.assertEqual(result, 1)
