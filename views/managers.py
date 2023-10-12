from django.db.models import Q, QuerySet, Prefetch, F, Subquery, OuterRef, Exists, Count
from django.db.models.functions import Length
from queryset_sequence import QuerySetSequence

from api.enums import ReactionType, ViewType
from arguments.enums import ArgumentReactionType
from arguments.models import Argument
from meda.managers import BaseManager


class ViewQuerySet(QuerySet):
    def get_user_views(self, user):
        return self.filter(user=user)

    def get_all_views(self):
        return self.filter(is_draft=False)

    def get_feed_views(self, user):
        from api.mixins import TrendingMixin

        following_ids = [
            following.pk for following in user.followings.all()] + [user.pk]

        trending_mixin = TrendingMixin()

        top_reactions = trending_mixin.sort_queryset_by_popularity(
            self.exclude(user=user).filter(
                parent_view=OuterRef('pk'), content__isnull=False)
        )

        top_my_reactions = trending_mixin.sort_queryset_by_popularity(
            self.filter(user=user, parent_view=OuterRef(
                'pk'), content__isnull=False)
        )

        return self.annotate(
            top_reaction_content=Subquery(top_reactions.values('content')[:1]),
            top_reaction_user_id=Subquery(top_reactions.values('user')[:1]),
            top_reaction_reaction_type=Subquery(
                top_reactions.values('reaction_type')[:1]),
            my_top_reaction_content=Subquery(
                top_my_reactions.values('content')[:1]),
            my_top_reaction_user_id=Subquery(
                top_my_reactions.values('user')[:1]),
            my_top_reaction_reaction_type=Subquery(
                top_my_reactions.values('reaction_type')[:1]),
            total_reactions=Count('view_reactions', filter=Q(
                view_reactions__content__isnull=False))
        ).filter(
            user__pk__in=following_ids, is_draft=False
        ).exclude(
            user=F('parent_view__user'), parent_view__isnull=False, content=None
        ).exclude(
            Q(user=F('parent_argument__moogt__proposition')) | Q(
                user=F('parent_argument__moogt__opposition')),
            parent_argument__isnull=False, content=None
        ).order_by('-created_at')

    def get_normal_views(self):
        return self.filter(Q(parent_view__isnull=True) & Q(parent_argument__isnull=True))

    def get_reaction_views(self):
        return self.annotate(content_length=Length('content')).filter(
            (Q(parent_view__isnull=False) | Q(parent_argument__isnull=False)) & Q(content_length__gt=0) & Q(
                content__isnull=False)
        )

    def get_one_time_reactions(self):
        return self.annotate(content_length=Length('content')).filter(
            (Q(parent_view__isnull=False) | Q(parent_argument__isnull=False)) & (
                Q(content_length=0) | Q(content__isnull=True))
        )

    def filter_using_search_term(self, search_term):
        return self.filter(content__icontains=search_term, is_draft=False)

    def filter_views_by_blocked_users(self, user):
        blocked_user_ids = user.blockings.annotate(
            block_user_id=F('blocked_user'))
        blocker_user_ids = user.blockers.annotate(block_user_id=F('user'))

        user_ids = QuerySetSequence(blocked_user_ids, blocker_user_ids).values_list(
            'block_user_id', flat=True)

        return self.exclude(
            user__pk__in=user_ids
        )


class ViewManager(BaseManager):

    def create(self, **kwargs):
        view = super().create(**kwargs)
        return view

    def get_queryset(self):
        """Perform necessary eager loading of data."""
        queryset = ViewQuerySet(
            self.model, using=self.db).filter(is_removed=False)
        return queryset.select_related(
            'stats',
            'user',
            'user__profile',
            'parent_view__stats',
            'parent_view__user',
            'parent_view__user__profile',
            'parent_argument__user',
            'parent_argument__user__profile',
        ).prefetch_related(
            'images',
            Prefetch(
                'view_reactions',
                queryset=queryset.filter(type=ViewType.VIEW_REACTION.name,
                                         reaction_type=ReactionType.ENDORSE.name),
                to_attr='endorsement_reactions'
            ),
            Prefetch(
                'view_reactions',
                queryset=queryset.filter(type=ViewType.VIEW_REACTION.name,
                                         reaction_type=ReactionType.DISAGREE.name),
                to_attr='disagreement_reactions'
            ),
            Prefetch(
                'stats__applauds',
                to_attr='view_applauds'
            ),
            Prefetch(
                'parent_view__view_reactions',
                queryset=queryset.filter(type=ViewType.VIEW_REACTION.name,
                                         reaction_type=ReactionType.ENDORSE.name),
                to_attr='endorsement_reactions'
            ),
            Prefetch(
                'parent_view__view_reactions',
                queryset=queryset.filter(type=ViewType.VIEW_REACTION.name,
                                         reaction_type=ReactionType.DISAGREE.name),
                to_attr='disagreement_reactions'
            ),
            Prefetch(
                'parent_view__stats__applauds',
                to_attr='view_applauds'
            ),
            Prefetch(
                'parent_argument__argument_reactions',
                queryset=queryset.filter(type=ViewType.ARGUMENT_REACTION.name),
                to_attr='reactions'
            ),
            Prefetch(
                'parent_argument__moogter_reactions',
                queryset=Argument.objects.filter(
                    reaction_type=ArgumentReactionType.ENDORSEMENT.name),
                to_attr='moogter_endorsement_reactions'
            ),
            Prefetch(
                'parent_argument__moogter_reactions',
                queryset=Argument.objects.filter(
                    reaction_type=ArgumentReactionType.DISAGREEMENT.name),
                to_attr='moogter_disagreement_reactions'
            ),
        )
