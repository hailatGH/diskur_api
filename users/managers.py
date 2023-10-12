from django.db.models import QuerySet, Count, Q, OuterRef, Exists, F
from django.contrib.auth.models import UserManager
from queryset_sequence import QuerySetSequence
# from django.contrib.auth.models import AnonymousUser


class MoogtMedaUserQuerySet(QuerySet):
    def annotate_follower_count(self):
        return self.annotate(followers_count=Count('followers'))


    def annotate_following_exists(self, user):
        followings_queryset = user.followings.filter(pk=OuterRef('pk'))
        return self.annotate(is_following=Exists(followings_queryset))

    def filter_using_search_term(self, search_term):
        return self.filter(Q(username__icontains=search_term) | Q(first_name__icontains=search_term))

    def annonate_with_blocking_status(self, user):
        from .models import Blocking
        is_blocked = Blocking.objects.filter(
            user=OuterRef('pk'), blocked_user=user)
        blocking = Blocking.objects.filter(
            user=user, blocked_user=OuterRef('pk'))
        return self.annotate(is_blocking=Exists(blocking), is_blocked=Exists(is_blocked))

    def filter_blocked_users(self, user):
        # if isinstance(user, AnonymousUser):
        #     return None
        
        blocked_users = user.blockings.annotate(block_user_id=F(
            'blocked_user'))
        blocker_users = user.blockers.annotate(block_user_id=F('user'))
        user_ids = QuerySetSequence(blocked_users, blocker_users).values_list(
            'block_user_id', flat=True)

        return self.exclude(id__in=user_ids)


class MoogtMedaUserManager(UserManager.from_queryset(MoogtMedaUserQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related('profile')
