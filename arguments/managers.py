from django.db.models import OuterRef, Exists, QuerySet, Prefetch, Manager
from model_utils.managers import SoftDeletableManager

from api.enums import ViewType
from arguments.enums import ArgumentReactionType
from meda.enums import ArgumentType


class ArgumentQuerySet(QuerySet):
    def prefetch_related_objects(self):
        from views.models import View
        reaction_views = View.objects.filter(parent_argument=OuterRef('pk'),
                                             content__isnull=False,
                                             type=ViewType.ARGUMENT_REACTION.name)

        reaction_arguments = self.filter(react_to=OuterRef('pk'))

        return self.annotate(
            has_reaction_views=Exists(reaction_views),
            has_reaction_arguments=Exists(reaction_arguments),
        ).select_related(
            'stats',
            'moogt',
        ).prefetch_related(
            Prefetch(
                'activities',
            ),
            Prefetch('activities__actor'),
            Prefetch('activities__actor__profile'),
            Prefetch('activities__user'),
            Prefetch('activities__user__profile'),
            Prefetch(
                'stats__applauds',
                to_attr='argument_applauds'
            ),
            Prefetch(
                'argument_reactions',
                to_attr='reactions'
            ),
            Prefetch(
                'moogter_reactions',
                queryset=self.filter(
                    reaction_type=ArgumentReactionType.ENDORSEMENT.name),
                to_attr='moogter_endorsement_reactions'
            ),
            Prefetch(
                'moogter_reactions',
                queryset=self.filter(
                    reaction_type=ArgumentReactionType.DISAGREEMENT.name),
                to_attr='moogter_disagreement_reactions'
            )
        )

    def get_user_arguments(self, user):
        return self.prefetch_related_objects().filter(user=user, type=ArgumentType.NORMAL.name)

    def filter_using_search_term(self, search_term):
        return self.filter(argument__icontains=search_term)


class ArgumentManager(SoftDeletableManager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'user',
            'user__profile',
        )


class ArgumentActivityManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('user', 'user__profile', 'actor', 'actor__profile')
