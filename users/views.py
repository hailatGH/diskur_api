
import json
import rest_framework.exceptions
import rest_framework.serializers
from rest_framework.settings import api_settings
from avatar.models import Avatar
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError, SuspiciousOperation, NON_FIELD_ERRORS
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import View as GenericView, DetailView
from rest_framework import generics, permissions, status
from dj_rest_auth.registration.views import RegisterView
from rest_framework.generics import RetrieveAPIView
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin
from rest_framework.parsers import MultiPartParser, FormParser
from arguments.extensions import BasicArgumentSerializerExtensions

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from views.extensions import BasicViewSerializerExtensions
from api.mixins import ReportMixin, SortCategorizeFilterMixin
from api.pagination import SmallResultsSetPagination
from arguments.models import Argument
from arguments.serializers import ArgumentSerializer
from chat import utils as chat_utils
from moogts.models import Moogt
from moogts.serializers import MoogtSerializer
from moogts.extensions import BasicMoogtExtensions
from moogts import utils
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from polls.models import Poll
from polls.serializers import PollSerializer
from views.models import View
from views.serializers import ViewSerializer
from .models import Blocking, PhoneNumber, Profile, MoogtMedaUser, Activity, ActivityType
from .serializers import AccountReportSerializer, MoogtMedaUserSerializer, ProfileModelSerializer, RefillWalletSerializer, UserProfileSerializer, PhoneNumberSignupSerializer
from users import utils as user_utils

from django.contrib.auth.models import AnonymousUser

class ProfileView(DetailView):
    """Renders the profile page for a given user."""
    model = Profile
    context_object_name = 'profile'
    template_name = "users/profile.html"
    queryset = MoogtMedaUser.objects.get_queryset()


class LoggedInProfileView(LoginRequiredMixin, ProfileView):
    """Renders the profile for a logged in user. If the user is not logged in,
    it redirects to the log-in page.
    """
    login_url = reverse_lazy('account_login')

    def get_object(self, queryset=None):
        return self.request.user.profile

    def get_context_data(self, **kwargs):
        context = super(LoggedInProfileView, self).get_context_data()
        context['is_self_profile'] = True
        return context


class AnonymousProfileView(ProfileView):
    """Renders the profile page of a user for a logged out user."""
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def get(self, request, *args, **kwargs):
        # If the user happens to be logged in, redirect to their
        # LoggedInProfileView.
        user = super(AnonymousProfileView, self).get_object()
        if request.user.is_authenticated and request.user.pk == user.pk:
            return redirect('users:logged_in_profile')
        return super(AnonymousProfileView, self).get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        user = super(AnonymousProfileView, self).get_object(queryset)
        return user.profile

    def get_context_data(self, **kwargs):
        context = super(AnonymousProfileView, self).get_context_data(**kwargs)
        context['is_self_profile'] = False
        user = super(AnonymousProfileView, self).get_object()
        context['can_follow_profile_owner'] = self.can_follow_profile_owner(
            self.request.user, user)
        return context

    @staticmethod
    def can_follow_profile_owner(user, profile_owner):
        if not user.is_authenticated:
            return False
        for follower in profile_owner.followers.all():
            if user == follower:
                return False
        return True


class FollowUserView(GenericView):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        followee_id = request.POST['followee_id']
        followee = get_object_or_404(MoogtMedaUser, pk=followee_id)

        self.validate_following(request.user, followee)

        followee.followers.add(request.user)
        request.user.followings.add(followee)
        Activity.record_activity(request.user.profile,
                                 ActivityType.follow_user.name, followee.id)
        return JsonResponse({"success": True})

    @staticmethod
    def validate_following(follower, followee):
        # Don't follow yourself!
        if follower == followee:
            raise ValidationError("Following self is not allowed.")

        # No duplicate followings.
        for existing_follower in followee.followers.all():
            if follower == existing_follower:
                raise ValidationError("Following already exists.")


class GetUsernamesAjaxView(GenericView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise SuspiciousOperation(
                "Unauthenticated user attempting to view usernames.")

        if 'q' not in request.GET:
            raise ValidationError("Invalid input. Query not found.")

        query = request.GET['q']

        users = MoogtMedaUser.objects.filter(username__icontains=query).order_by(
            'username').exclude(username=request.user.username)[:5]

        # usernames = [moogter_user_display(user) for user in users]
        # For now we just need the username of the matched users but it is also to include the users avatar
        usernames = [{'id': user.id, 'text': f'@{user.username}'}
                     for user in users]
        return JsonResponse({'results': usernames}, safe=False)


class GetUsernamesApiView(generics.ListAPIView):
    serializer_class = MoogtMedaUserSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', None)

        if not query:
            raise rest_framework.exceptions.ValidationError(
                'Invalid Input. Query not found.')

        elif query[0] == '@':
            query = query[1:]
            
        if isinstance(self.request.user, AnonymousUser):
            users = MoogtMedaUser.objects.filter(Q(first_name__istartswith=query) | Q(username__istartswith=query))
        else:
            users = MoogtMedaUser.objects.filter(Q(first_name__istartswith=query) | Q(username__istartswith=query)) .exclude(
                username=self.request.user.username).exclude(username=self.request.user.username)

            users = users.filter_blocked_users(self.request.user)

            # If you include who to exclude
            exclude = self.request.query_params.get('exclude', None)
            if exclude:
                user_to_exclude = get_object_or_404(MoogtMedaUser, pk=exclude)
                users = users.exclude(username=user_to_exclude.username)

            moogt = self.request.query_params.get('moogt', None)
            if moogt:
                moogt = get_object_or_404(Moogt, pk=moogt)
                invitation = moogt.invitations.first()
                if invitation:
                    users = users.exclude(
                        username__in=[invitation.get_inviter().username, invitation.get_invitee().username])
                    
        return users[:5]


class FollowUserApiView(generics.GenericAPIView):
    serializer_class = MoogtMedaUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        followee_id = kwargs.get('pk')
        followee = get_object_or_404(MoogtMedaUser, pk=followee_id)

        self.validate_following(request.user, followee)

        (conversation, _) = chat_utils.get_or_create_conversation(
            request.user, followee)
        priority_conversations = request.user.priority_conversations

        if followee.followers.filter(pk=request.user.pk).exists():
            followee.followers.remove(request.user)
            request.user.followings.remove(followee)
            Notification.objects.remove_notification(
                followee,
                request.user,
                NOTIFICATION_TYPES.user_follow)

            if priority_conversations.filter(pk=conversation.pk).exists():
                priority_conversations.remove(conversation)
            Activity.record_activity(
                request.user.profile, ActivityType.unfollow_user.name, followee.id)
        else:
            followee.followers.add(request.user)
            request.user.followings.add(followee)

            priority_conversations.add(conversation)

            notify.send(
                recipient=followee,
                sender=request.user,
                verb="followed",
                target=followee,
                type=NOTIFICATION_TYPES.user_follow,
                send_email=False,
                send_telegram=True,
                push_notification_title=f'{request.user} subscribed to you',
            )

            Activity.record_activity(
                request.user.profile, ActivityType.follow_user.name, followee.id)

        followee = MoogtMedaUser.objects.annotate_follower_count(
        ).annotate_following_exists(request.user).get(pk=followee.id)
        return Response(self.get_serializer(followee).data, status=status.HTTP_200_OK)

    @staticmethod
    def validate_following(follower, followee):
        # Don't follow yourself!
        if not follower.can_follow(followee):
            raise rest_framework.exceptions.ValidationError(
                "Self following is not allowed.")

        has_blocked_user = follower.blockings.filter(
            blocked_user=followee).exists()

        if has_blocked_user:
            raise rest_framework.exceptions.PermissionDenied(
                'You cannot follow a user that you have blocked!')

        is_blocked = follower.blockers.filter(user=followee).exists()

        if is_blocked:
            raise rest_framework.exceptions.PermissionDenied(
                'You cannot follow a user that have blocked you!'
            )


class UserProfileApiView(SerializerExtensionsAPIViewMixin,
                         ListModelMixin,
                         SortCategorizeFilterMixin,
                         generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = SmallResultsSetPagination
    user = None

    def get(self, request, *args, **kwargs):
        user_id = self.kwargs.get('pk')
        self.user = get_object_or_404(MoogtMedaUser, pk=user_id)

        items = self.list(request, *args, **kwargs).data

        data = {
            'user': self.user,
            'items': items
        }

        return Response(self.get_user_profile_serializer(data).data, status.HTTP_200_OK)

    def get_serializer_class(self, *args, **kwargs):
        item_type = self.request.query_params.get('item_type', 'moogt')
        if item_type == "moogt":
            return MoogtSerializer
        elif item_type == "view":

            return ViewSerializer
        elif item_type == "poll":
            return PollSerializer
        elif item_type == 'argument':
            return ArgumentSerializer

    def get_user_profile_serializer(self, data):
        data = {'user': data.get('user'),
                'items': data.get('items'),
                }

        return UserProfileSerializer(data, context={'request': self.request})

    def get_queryset(self):
        item_type = self.request.query_params.get('item_type', 'moogt')
        search_term = self.request.query_params.get('q')

        if item_type == "moogt":

            return self.get_moogts(search_term)
        elif item_type == "view":
            return self.get_views(search_term)
        elif item_type == "poll":
            return self.get_polls(search_term)
        elif item_type == 'argument':
            return self.get_arguments(search_term)

    def get_serializer_context(self):
        item_type = self.request.query_params.get('item_type')
        context = super().get_serializer_context()

        if item_type == 'view':
            return {
                **context,
                'expand': BasicViewSerializerExtensions.extensions_expand

            }
        if item_type == 'moogt':
            return {
                **context,
                'expand': BasicMoogtExtensions.extensions_expand
            }

        if item_type == 'argument':
            return {
                **context,
                'expand': BasicArgumentSerializerExtensions.extensions_expand
            }

        return context

    def get_moogts(self, search_term):
        queryset = Moogt.objects.get_all_moogts(
        ).get_participating_moogts(self.kwargs.get('pk'))

        category = self.request.query_params.get('category', 'live')
        sort_by = self.request.query_params.get('sort_by', 'date')

        return self.categorize_and_sort_moogts(queryset, search_term, sort_by, category)

    def get_views(self, search_term):
        queryset = View.objects.get_user_views(self.user).get_all_views()
        sort_by = self.request.query_params.get('sort_by', 'date')
        category = self.request.query_params.get('category', 'view')

        return self.categorize_and_sort_views(queryset, search_term, sort_by, category)

    def get_polls(self, search_term):
        queryset = Poll.objects.get_user_polls(
            self.user).get_polls_for_user(self.request.user)
        category = self.request.query_params.get('category', 'live')
        sort_by = self.request.query_params.get('sort_by', 'date')

        return self.categorize_and_sort_polls(queryset, search_term, sort_by, category)

    def get_extensions_mixin_context(self):
        context = super(UserProfileApiView,
                        self).get_extensions_mixin_context()
        item_type = self.request.query_params.get('item_type', 'moogt')

        expand = []

        if item_type == "moogt":
            expand += ['proposition', 'opposition', 'banner']
        elif item_type == "view":
            # add images to the profile page of Views
            expand += ['user', 'stats', 'images']
        elif item_type == "poll":
            expand += ['options', 'user']
        elif item_type == "argument":
            expand += ['images']

        context['expand'] = set(expand)

        return context

    def get_arguments(self, search_term):
        queryset = Argument.objects.get_user_arguments(self.user)
        sort_by = self.request.query_params.get('sort_by', 'date')

        return self.sort_arguments(queryset, search_term, sort_by)


class GetProfileItemsCountApiView(generics.GenericAPIView):
    """Get the number of items created by a user."""

    def get(self, request, *args, **kwargs):
        user_id = kwargs.get('pk')
        user = get_object_or_404(MoogtMedaUser, pk=user_id)
        search_term = self.request.query_params.get('q')

        count = {
            'moogts_count': self.get_moogts_count(user, search_term),
            'views_count': self.get_views_count(user, search_term),
            'polls_count': self.get_polls_count(user, search_term),
            'arguments_count': self.get_arguments_count(user, search_term),
        }

        return Response(count)

    def get_moogts_count(self, user, search_term):
        queryset = Moogt.objects.get_all_moogts().get_participating_moogts(user.id)
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        return queryset.count()

    def get_views_count(self, user, search_term):
        queryset = View.objects.get_user_views(user)
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        return queryset.count()

    def get_polls_count(self, user, search_term):
        queryset = Poll.objects.get_user_polls(user)
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        return queryset.count()

    def get_arguments_count(self, user, search_term):
        queryset = Argument.objects.get_user_arguments(user)

        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        return queryset.count()


class EditProfileApiView(SerializerExtensionsAPIViewMixin, generics.UpdateAPIView):
    serializer_class = MoogtMedaUserSerializer
    extensions_expand = ['profile']
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = get_object_or_404(MoogtMedaUser, pk=request.user.pk)
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status.HTTP_200_OK)


class ProfilePhotoUploadApiView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView):
    serializer_class = MoogtMedaUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    extensions_expand = ['profile']

    def post(self, request, *args, **kwargs):
        serializer = ProfileModelSerializer(instance=request.user.profile,
                                            data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(self.get_serializer(request.user).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RemoveProfileImagesApiView(generics.GenericAPIView):
    serializer_class = MoogtMedaUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        delete_avatar = request.data.get('avatar', False)
        delete_cover = request.data.get('cover', False)

        if delete_avatar:
            Avatar.objects.filter(user=request.user).delete()
        if delete_cover:
            request.user.cover = None
        request.user.save()

        serializer = self.get_serializer(request.user)

        return Response(serializer.data, status.HTTP_200_OK)


class UsersListApiView(generics.ListAPIView):
    serializer_class = MoogtMedaUserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'first_name', 'last_name', 'email']

    def get_queryset(self):
        return MoogtMedaUser.objects.exclude(id=self.request.user.id)


class UserDetailApiView(RetrieveAPIView):
    serializer_class = MoogtMedaUserSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = MoogtMedaUser.objects.all().annotate_follower_count()

        if self.request.user.is_authenticated:
            queryset = queryset.annonate_with_blocking_status(
                self.request.user).annotate_following_exists(self.request.user)

        return queryset


class GetSubscriptionInfo(generics.ListAPIView):
    serializer_class = MoogtMedaUserSerializer
    pagination_class = SmallResultsSetPagination

    def get_queryset(self):
        subscribed_only = json.loads(
            self.request.query_params.get('subscribed_only', 'false'))
        if subscribed_only:
            queryset = self.request.user.followings.all()
        else:
            queryset = self.request.user.followers.all()

        return queryset.annotate_follower_count().annotate_following_exists(self.request.user).filter_blocked_users(self.request.user)


class RecommendedAccountsApiView(generics.ListAPIView):
    serializer_class = MoogtMedaUserSerializer
    pagination_class = SmallResultsSetPagination

    def get_queryset(self):
        if isinstance(self.request.user, AnonymousUser):
            users = MoogtMedaUser.objects.all()
                
        else:
            users = MoogtMedaUser.objects \
                .filter_blocked_users(self.request.user) \
                .annotate(followers_count=Count('follower')) \
                .exclude(pk__in=self.request.user.followings.values_list('pk', flat=True)) \
                .exclude(pk=self.request.user.pk) \
                .exclude(is_staff=True) \
                .order_by('-followers_count')

        return users


class RefillWalletApiView(generics.GenericAPIView):
    serializer_class = RefillWalletSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            amount = serializer.get_amount()
            wallet = self.request.user.wallet
            wallet.credit = wallet.credit + amount
            wallet.save()

            return Response({'wallet': wallet.credit})


class BlockUserApiView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        user_id = kwargs.get('pk', None)
        user_to_be_blocked = get_object_or_404(MoogtMedaUser, pk=user_id)

        blocking_exists = Blocking.objects.filter(
            user=request.user, blocked_user=user_to_be_blocked).exists()

        if blocking_exists:
            is_blocked = self.unblock_user(request.user, user_to_be_blocked)
        else:
            is_blocked = self.block_user(request.user, user_to_be_blocked)

        return Response({'is_blocked': is_blocked})

    def unblock_user(self, user: MoogtMedaUser, blocked_user: MoogtMedaUser) -> bool:
        blocking = Blocking.objects.get(user=user, blocked_user=blocked_user)
        blocking.delete()

        chat_utils.unlock_conversation(user, blocked_user)
        return False

    def block_user(self, user: MoogtMedaUser, blocked_user: MoogtMedaUser) -> bool:
        try:
            blocking = Blocking(user=user, blocked_user=blocked_user)
            blocking.full_clean()
            blocking.save()

            user.followings.remove(blocked_user)
            blocked_user.followers.remove(user)
            blocked_user.followings.remove(user)
            user.followers.remove(blocked_user)

            chat_utils.lock_conversation(user, blocked_user)
            utils.find_and_quit_moogts(user, blocked_user)
            utils.maybe_unfollow_moogts(follower=user)
        except ValidationError as e:
            raise rest_framework.exceptions.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: e.message_dict[NON_FIELD_ERRORS]})
        return True


class BlockedUsersListApiView(generics.ListAPIView):
    serializer_class = MoogtMedaUserSerializer

    def get_queryset(self):
        blocked_user_ids = Blocking.objects.filter(
            user=self.request.user).values_list('blocked_user', flat=True)
        return MoogtMedaUser.objects.filter(id__in=blocked_user_ids)

class ReportAccountApiView(ReportMixin, generics.CreateAPIView):
    serializer_class = AccountReportSerializer
    
    def post(self, request, *args, **kwargs):
        account_id = kwargs.get('pk')
        self.account = get_object_or_404(MoogtMedaUser, pk=account_id)
        
        self.validate(created_by=self.account, reported_by=self.request.user, queryset=self.account.reports.all())
        
        return super().post(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        report = serializer.save(user=self.account, reported_by=self.request.user)
        self.notify_admins(report)

class RegisterWithPhoneApiView(RegisterView):
    serializer_class = PhoneNumberSignupSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        firebase_response = user_utils.verify_firebase_user(serializer.data['firebase_token'])
        if not firebase_response:
            raise rest_framework.exceptions.ValidationError("Issues with firebase token.")
        
        user = super().perform_create(serializer)
        PhoneNumber.objects.create(
            user=user, 
            phone_number=serializer.data['phone_number'], 
            firebase_uid=firebase_response['uid'], 
            is_verified=True
        )
        
        return user