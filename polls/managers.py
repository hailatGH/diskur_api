from django.db.models import Count, QuerySet, OuterRef, Exists
from django.db.models import Manager, Q, F
from django.utils import timezone
from queryset_sequence import QuerySetSequence

from meda.managers import BaseManager


class PollOptionManager(Manager):
    def get_queryset(self):
        return super(PollOptionManager, self).get_queryset().annotate(
            vote_count=Count('votes'))


class PollQuerySet(QuerySet):
    def get_user_polls(self, user):
        return self.filter(user=user)

    def get_live_polls(self):
        return self.filter(end_date__gt=timezone.now())

    def get_closed_polls(self):
        return self.filter(end_date__lt=timezone.now())

    def filter_using_search_term(self, search_term):
        return self.filter(Q(title__icontains=search_term) | Q(options__content__icontains=search_term))

    def get_polls_for_user(self, user):
        if user and user.id:
            from polls.models import PollOption

            options = PollOption.objects.filter(
                votes=user, poll=OuterRef('pk'))
            return self.annotate(can_vote=Exists(options, negated=True))
        return self

    def filter_poll_by_blocked_user(self, user):
        blocked_user_ids = user.blockings.annotate(
            block_user_id=F('blocked_user'))
        blocker_user_ids = user.blockers.annotate(block_user_id=F('user'))

        user_ids = QuerySetSequence(blocked_user_ids, blocker_user_ids).values_list(
            'block_user_id', flat=True)

        return self.exclude(user_id__in=user_ids)


class PollManager(BaseManager):
    def get_queryset(self):
        return super(PollManager, self).get_queryset().select_related(
            'stats',
            'user',
            'user__profile'
        ).prefetch_related(
            'options',
            # 'options__votes'
        ).annotate(total_vote=Count('options__votes'))

    def create(self, **kwargs):
        options = kwargs.pop('options')

        poll = super().create(**kwargs)
        poll.end_date = poll.start_date + kwargs.get('max_duration')
        poll.save()
        poll.create_options(options)

        return self.get_queryset().get(pk=poll.id)
