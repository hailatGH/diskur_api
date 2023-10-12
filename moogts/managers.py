from django.db.models import Manager
from django.db.models import F, Count, Q, Prefetch, QuerySet, Sum, Case, When
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from queryset_sequence import QuerySetSequence

from meda.enums import ArgumentType
from meda.managers import BaseManager
from users.models import Activity, ActivityType


class MoogtQuerySet(QuerySet):
    def get_participating_moogts(self, id):
        return self.filter(Q(proposition=id) | Q(opposition=id) | Q(moderator=id))

    def get_premiering_moogts(self):
        return self.filter(is_premiering=True, premiering_date__isnull=False)

    def get_non_premiering_moogts(self):
        return self.filter(is_premiering=False)

    def get_live_moogts(self):
        return self.filter(is_paused=False, has_ended=False, started_at__isnull=False)

    def get_all_moogts(self):
        return self.filter(Q(started_at__isnull=False) | Q(is_premiering=True, premiering_date__isnull=False))

    def get_user_moogts(self, user):
        return self.filter(Q(proposition=user) | Q(opposition=user) | Q(moderator=user))

    def get_feed_moogts(self, user):
        # TODO: Use Subqueries to find moogts that belong to users that you are following
        following_ids = [
            following.pk for following in user.followings.all()] + [user.pk]

        return self.get_all_moogts() \
            .filter(  # moogts from proposition or opposition you are following
            Q(proposition__pk__in=following_ids) | Q(opposition__pk__in=following_ids) | Q(moderator__pk__in=following_ids))

    def get_ended_moogts(self):
        return self.filter(has_ended=True)

    def get_paused_moogts(self):
        return self.filter(is_paused=True)

    def filter_using_search_term(self, search_term):
        return self.filter(Q(resolution__icontains=search_term) |
                           Q(description__icontains=search_term) |
                           Q(proposition__first_name__icontains=search_term) |
                           Q(opposition__first_name__icontains=search_term) |
                           Q(proposition__username__icontains=search_term) |
                           Q(opposition__username__icontains=search_term))

    def filter_moogts_by_blocked_users(self, user):
        blocked_user_ids = user.blockings.annotate(block_user_id=F(
            'blocked_user'))

        blocker_user_ids = user.blockers.annotate(
            block_user_id=F('user'))

        user_ids = QuerySetSequence(blocked_user_ids, blocker_user_ids).values_list(
            'block_user_id', flat=True)

        return self.exclude(Q(
            Q(proposition__id__in=user_ids) &
            Q(opposition__id__in=user_ids) &
            Q(
                Q(moderator__isnull=True) |
                Q(moderator__id__in=user_ids)
            )
        )
        )


class MoogtManager(BaseManager):
    def get_queryset(self):
        from .models import MoogtActivity, ActivityStatus

        return super().get_queryset().annotate(
            followers_count=Count('followers')
        ).select_related(
            'stats',
            'proposition',
            'opposition',
            'moderator',
            'proposition__profile',
            'opposition__profile',
            'moderator__profile',
        ).prefetch_related(
            'arguments',
            'arguments__argument_reactions',
            'arguments__argument_reactions__user',
            'tags',
            'invitations',
            Prefetch('activities',
                     queryset=MoogtActivity.objects.filter(Q(status=ActivityStatus.PENDING.value) | Q(status=ActivityStatus.WAITING.value)).prefetch_related(
                         'actions__actor__profile',
                     )
                     ),
            Prefetch(
                'opposition__followers',
                to_attr='opposition_followers'
            ),
            Prefetch(
                'proposition__followers',
                to_attr='proposition_followers'
            )
        ).annotate(
            # TODO: find a better fix
            arguments_count=Count('arguments',
                                  distinct=True,
                                  filter=Q(arguments__type=ArgumentType.NORMAL.name) | Q(
                                      arguments__type=ArgumentType.REACTION.name)),

            proposition_endorsement=Sum(
                Case(When(proposition=F('arguments__user'), then=F('arguments__stats__endorsement_count')))),
            proposition_disagreement=Sum(
                Case(When(proposition=F('arguments__user'), then=F('arguments__stats__disagreement_count')))),
            opposition_endorsement=Sum(
                Case(When(opposition=F('arguments__user'), then=F('arguments__stats__endorsement_count')))),
            opposition_disagreement=Sum(
                Case(When(opposition=F('arguments__user'), then=F('arguments__stats__disagreement_count')))),
        )

    def get_started_moogts(self):
        return self.exclude(Q(is_premiering=False) & Q(started_at=None))

    def create(self, **kwargs):
        kwargs['next_turn_proposition'] = True

        moogt = super().create(**kwargs)
        try:
            activity = Activity()
            activity.profile = moogt.get_proposition().profile
            activity.type = ActivityType.create_moogt.name
            activity.object_id = moogt.id
            activity.save()
        except ObjectDoesNotExist:
            pass

        return moogt


class DonationManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'user',
            'user__profile',
        )


class MoogtStatusManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'user',
            'user__profile',
        )


class MoogtActivityManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related(
            'user',
            'user__profile',
            'actor',
            'actor__profile',
        )
