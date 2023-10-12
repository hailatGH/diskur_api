import rest_framework
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from avatar.conf import settings as avatar_settings
from avatar.models import Avatar
from avatar.signals import avatar_deleted, avatar_updated
from avatar.utils import get_primary_avatar, invalidate_cache
from django.db.models import Sum, IntegerField, Count
from django.shortcuts import get_object_or_404
import six
from django_comments_xtd.api.serializers import WriteCommentSerializer
from django_comments_xtd.models import XtdComment, MaxThreadLevelExceededException
from drf_multiple_model.views import FlatMultipleModelAPIView
from dynamic_preferences.users.models import UserPreferenceModel
from dynamic_preferences.users.viewsets import UserPreferencesViewSet
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework import generics, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin
from rest_framework_jwt.views import ObtainJSONWebToken

from arguments.models import Argument
from arguments.serializers import ArgumentSerializer
from invitations.models import Invitation
from meda.enums import InvitationStatus
from moogter_bot.bot import bot
from arguments.extensions import BasicArgumentSerializerExtensions
from moogts.extensions import BasicMoogtExtensions
from moogts.models import Moogt
from moogts.serializers import MoogtSerializer
from notifications.models import NOTIFICATION_TYPES
from notifications.signals import notify
from polls.models import Poll
from polls.serializers import PollSerializer
from users.models import MoogtMedaUser
from users.serializers import MoogtMedaUserSerializer
from views.extensions import BasicViewSerializerExtensions
from views.models import View
from views.serializers import ViewSerializer
from .enums import Visibility
from .mixins import CommentMixin, SortCategorizeFilterMixin
from .models import TelegramChatToUser
from .pagination import MultiModelLimitOffsetPagination, StandardResultsSetPagination, SmallResultsSetPagination
from .serializers import (AvatarSerializer, TelegramChatToUserSerializer,
                          SidebarSerializer, CommentSerializer, CommentNotificationSerializer,
                          FirebaseJSONWebTokenSerializer)


class PreferencesViewSet(UserPreferencesViewSet):
    """
    We are extending from the UserPreferencesViewSet of django-dynamic-preferences
    """

    @action(detail=False)
    def sections(self, request, *args, **kwargs):
        """
        Returns the list of preference sections (those created
        inside user/dynamic_preferences_registry.py file)
        """
        sections = UserPreferenceModel.objects.values_list(
            'section', flat=True).distinct()
        return Response(sections, status=status.HTTP_200_OK)


class RenderPrimaryAvatarView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AvatarSerializer

    def get(self, request, *args, **kwargs):
        user = kwargs.get('user')

        size = kwargs.get('size')
        if size is None:
            size = avatar_settings.AVATAR_DEFAULT_SIZE

        avatar = get_primary_avatar(user, size=int(size))
        avatar_serializer = self.get_serializer(avatar)

        return Response(avatar_serializer.data, status=status.HTTP_200_OK)


class AddAvatarView(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = AvatarSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        image_file = request.FILES.get('avatar', None)

        if image_file is None:
            return Response('Image file is required.', status=status.HTTP_400_BAD_REQUEST)

        avatar = Avatar(user=request.user, primary=True)
        avatar.avatar.save(image_file.name, image_file)
        avatar.save()
        avatar_updated.send(sender=Avatar, user=request.user, avatar=avatar)
        avatar_serializer = self.get_serializer(avatar)

        return Response(avatar_serializer.data, status=status.HTTP_201_CREATED)


class AvatarListView(generics.ListAPIView):
    serializer_class = AvatarSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        avatars = self.request.user.avatar_set.all().order_by('-date_uploaded')

        if avatar_settings.AVATAR_MAX_AVATARS_PER_USER == 1:
            avatars = avatars[:1]
        else:
            # Slice the default set now that we used
            # the queryset for the primary avatar
            avatars = avatars[:avatar_settings.AVATAR_MAX_AVATARS_PER_USER]

        return avatars


class ChangeAvatarView(generics.GenericAPIView):
    serializer_class = AvatarSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        choice = request.data.get('choice')
        if not choice:
            return Response('You must select your choice!', status=status.HTTP_400_BAD_REQUEST)

        avatar = get_object_or_404(Avatar, pk=choice)
        avatar.primary = True
        avatar.save()
        invalidate_cache(request.user)
        avatar_updated.send(sender=Avatar, user=request.user, avatar=avatar)

        avatar_serializer = self.get_serializer(avatar)
        return Response(avatar_serializer.data, status=status.HTTP_200_OK)


class DeleteAvatarView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AvatarSerializer

    def post(self, request, *args, **kwargs):
        avatars = self.request.user.avatar_set.all()
        avatar = get_primary_avatar(request.user.username, size=int(
            avatar_settings.AVATAR_DEFAULT_SIZE))

        ids = request.data.get('choices')

        for a in avatars:
            if six.text_type(a.id) in ids:
                avatar_deleted.send(sender=Avatar, user=request.user,
                                    avatar=a)

        if avatars.count() > len(ids) and six.text_type(avatar.id) in ids:
            # Find the next best avatar, and set it as the new primary
            for a in avatars:
                if six.text_type(a.id) not in ids:
                    a.primary = True
                    a.save()
                    avatar_updated.send(sender=Avatar, user=request.user,
                                        avatar=avatar)
                    break
        Avatar.objects.filter(id__in=ids).delete()

        avatar = get_primary_avatar(request.user.username, size=int(
            avatar_settings.AVATAR_DEFAULT_SIZE))
        avatar_serializer = self.get_serializer(avatar)
        return Response(avatar_serializer.data, status=status.HTTP_200_OK)


class GetPublicityStatusView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = Visibility.all()

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return Response(queryset, status=status.HTTP_200_OK)


class SideBarApiView(generics.GenericAPIView):
    def get(self, request, *args, **kwargs):
        moogt_count = Moogt.objects.filter(proposition=request.user).count()

        user = MoogtMedaUser.objects.get(pk=request.user.id)

        subscriber_count = user.followers.count()
        subscribed_count = user.followings.count()

        open_invitation_count = Invitation.objects.filter(inviter=request.user,
                                                          invitee=None, status=InvitationStatus.PENDING.name).count()

        wallet_amount = user.wallet.credit
        donations_amount = user.donations.aggregate(
            Sum('amount', output_field=IntegerField()))['amount__sum']

        if donations_amount == None:
            donations_amount = 0

        sidebar_data = {"moogt_count": moogt_count,
                        "subscriber_count": subscriber_count,
                        "subscribed_count": subscribed_count,
                        "open_invitation_count": open_invitation_count,
                        "donations_amount": donations_amount,
                        "wallet_amount": wallet_amount}

        serializer = SidebarSerializer(sidebar_data)
        return Response(serializer.data, status.HTTP_200_OK)


class FeedContentApiView(FlatMultipleModelAPIView):
    pagination_class = MultiModelLimitOffsetPagination
    sorting_fields = ['-created_at']

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_querylist(self):
        user = MoogtMedaUser.objects.get(pk=self.request.user.id)
        following_ids = [
            following.pk for following in user.followings.all()] + [user.pk]
        querylist = [
            {
                'queryset': Moogt.objects.get_feed_moogts(user=self.request.user).order_by('-created_at'),
                'serializer_class': MoogtSerializer,
                'label': 'moogt',
                'expand': {'banner'}
            },
            {
                'queryset': View.objects.get_feed_views(self.request.user).filter_views_by_blocked_users(self.request.user),
                'serializer_class': ViewSerializer,
                'label': 'view',
                'expand': BasicViewSerializerExtensions.extensions_expand
            },
            {
                'queryset': self.get_polls(following_ids).filter_poll_by_blocked_user(self.request.user),
                'serializer_class': PollSerializer,
                'label': 'poll',
            }

        ]
        return querylist

    def get_polls(self, following_ids):
        return Poll.objects.filter(user__pk__in=following_ids).order_by('-created_at').get_polls_for_user(
            self.request.user)

    def list(self, request, *args, **kwargs):
        querylist = self.get_querylist()

        results = self.get_empty_results()

        for query_data in querylist:
            self.check_query_data(query_data)

            queryset = self.load_queryset(query_data, request, *args, **kwargs)

            # Run the paired serializer
            context = self.get_serializer_context()
            context['expand'] = query_data.get('expand', [])
            data = query_data['serializer_class'](
                queryset, many=True, context=context).data

            label = self.get_label(queryset, query_data)

            # Add the serializer data to the running results tally
            results = self.add_to_results(data, label, results)

        formatted_results = self.format_results(results, request)

        if self.is_paginated:
            try:
                formatted_results = self.paginator.format_response(
                    formatted_results)
            except AttributeError:
                raise NotImplementedError(
                    "{} cannot use the regular Rest Framework or Django paginators as is. "
                    "Use one of the included paginators from `drf_multiple_models.pagination "
                    "or subclass a paginator to add the `format_response` method."
                    "".format(self.__class__.__name__)
                )

        return Response(formatted_results)

    def add_to_results(self, data, label, results):
        """
        Adds the label to the results, as needed, then appends the data
        to the running results tab
        """
        for datum in data:
            if label is not None:
                datum.update({'item_type': label})

            results.append(datum)

        return results


class ReplyCommentApiView(CommentMixin, generics.GenericAPIView):
    serializer_class = WriteCommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        original = get_object_or_404(
            XtdComment, pk=request.data.get('reply_to'))
        try:
            if not original.allow_thread():
                raise MaxThreadLevelExceededException(original)

            comment = self.comment(request, original)
            serializer = CommentSerializer(
                comment, context=self.get_serializer_context())

            if isinstance(comment.content_object.content_object, Argument):
                push_notification_description = f'{request.user} replied to your Comment,"{original.comment}" on the Moogt Card, "{comment.content_object.content_object}"'
            if isinstance(comment.content_object.content_object, View):
                push_notification_description = f'{request.user} replied to your Comment,"{original.comment}" on the View, "{comment.content_object.content_object}"'
            if isinstance(comment.content_object.content_object, Poll):
                push_notification_description = f'{request.user} replied to your Comment,"{original.comment}" on the Poll, "{comment.content_object.content_object}"'
            else:
                push_notification_description = f'{request.user} replied to your Comment,"{original.comment}"'

            if request.user != original.user:
                notify.send(
                    recipient=original.user,
                    sender=self.request.user,
                    verb="replied",
                    target=original,
                    send_email=False,
                    send_telegram=True,
                    type=NOTIFICATION_TYPES.comment_reply,
                    data={
                        'original': CommentNotificationSerializer(original, context=self.get_serializer_context()).data,
                        'reply': serializer.data
                    },
                    push_notification_title=f'{self.request.user} replied to your Comment!',
                    push_notification_description=push_notification_description)

            return Response(serializer.data, status.HTTP_201_CREATED)
        except MaxThreadLevelExceededException as exc:
            raise rest_framework.exceptions.ValidationError(exc)


class LikeCommentApiView(CommentMixin, generics.GenericAPIView):

    def post(self, request, *args, **kwargs):
        comment = get_object_or_404(XtdComment,
                                    pk=kwargs.get('pk'))

        return Response({'success': self.like_comment(request, comment)}, status.HTTP_200_OK)


class UnlikeCommentApiView(CommentMixin, generics.GenericAPIView):

    def post(self, request, *args, **kwargs):
        comment = get_object_or_404(XtdComment,
                                    pk=kwargs.get('pk'))

        return Response({'success': self.unlike_comment(request, comment)}, status.HTTP_200_OK)


class BrowseCommentReplyApiView(SerializerExtensionsAPIViewMixin, CommentMixin, generics.ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = SmallResultsSetPagination
    extensions_expand = ['user__profile']

    def get_queryset(self):
        parent_id = self.kwargs.get('pk')
        xtd_comment = get_object_or_404(XtdComment, pk=parent_id)
        return self.get_comments(self.request, xtd_comment)


class RemoveCommentApiView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        comment = get_object_or_404(XtdComment,
                                    pk=kwargs.get('pk'))

        if comment.user != request.user:
            raise PermissionDenied('You cannot remove this comment.')

        comment.is_public = False
        comment.save(update_fields=['is_public'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentDetailApiView(generics.RetrieveAPIView):
    queryset = XtdComment.objects.all()
    serializer_class = CommentSerializer


class SearchResultsApiView(generics.ListAPIView,
                           SortCategorizeFilterMixin):

    def get_queryset(self):
        search_term = self.request.query_params.get('q')
        if (search_term is not None):
            search_term = search_term.strip()
        sort_by = self.request.query_params.get('sort_by', 'date')

        if not search_term:
            raise rest_framework.exceptions.ParseError(
                'You must provide the search term.')

        item_type = self.request.query_params.get('item_type')
        if item_type == 'view':
            return self.get_views(search_term, sort_by)

        if item_type == 'argument':
            return self.get_arguments(search_term, sort_by)

        if item_type == 'user':
            return self.get_users(search_term, sort_by)

        if item_type == 'poll':
            return self.get_polls(search_term, sort_by)

        return self.get_moogts(search_term, sort_by)

    def get_serializer_class(self):
        item_type = self.request.query_params.get('item_type')
        if item_type == 'view':
            return ViewSerializer
        if item_type == 'argument':
            return ArgumentSerializer
        if item_type == 'user':
            return MoogtMedaUserSerializer
        if item_type == 'poll':
            return PollSerializer

        return MoogtSerializer

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

    def get_views(self, search_term, sort_by):
        queryset = View.objects.get_all_views()
        if self.request.user.is_authenticated:
            queryset = queryset.filter_views_by_blocked_users(
                self.request.user)

        category = self.request.query_params.get('category', 'view')
        return self.categorize_and_sort_views(queryset, search_term, sort_by, category)

    def get_users(self, search_term, sort_by):
        category = self.request.query_params.get('category', 'view')
        queryset = self.categorize_and_sort_users(
            MoogtMedaUser.objects.exclude(
                pk=self.request.user.pk).annotate_follower_count(), search_term, sort_by,
            category)

        if self.request.user.is_authenticated:
            queryset = queryset.filter_blocked_users(self.request.user)

        return queryset

    def get_arguments(self, search_term, sort_by):
        queryset = Argument.objects.filter_using_search_term(search_term)

        if sort_by == 'date':
            queryset = queryset.order_by("-created_at")
        else:
            queryset = queryset.annotate(reaction_count=Count(
                'argument_reactions')).order_by('-reaction_count')

        return queryset

    def get_moogts(self, search_term, sort_by):
        queryset = Moogt.objects.get_all_moogts()
        if self.request.user.is_authenticated:
            queryset = queryset.filter_moogts_by_blocked_users(
                self.request.user)
        category = self.request.query_params.get('category', 'live')
        return self.categorize_and_sort_moogts(queryset, search_term, sort_by, category)

    def get_polls(self, search_term, sort_by):
        queryset = Poll.objects.all()
        if self.request.user:
            queryset = queryset.get_polls_for_user(
                self.request.user).filter_poll_by_blocked_user(self.request.user)
        category = self.request.query_params.get('category', 'live')
        return self.categorize_and_sort_polls(queryset, search_term, sort_by, category)


class SearchResultsCountApiView(generics.GenericAPIView):
    def get(self, request, *args, **kwargs):
        search_term = request.query_params.get('q')
        if not search_term:
            raise rest_framework.exceptions.ValidationError(
                'You must provide the search term.')

        count = {
            'moogts_count': self.get_moogts_count(search_term),
            'views_count': self.get_views_count(search_term),
            'polls_count': self.get_polls_count(search_term),
            'arguments_count': self.get_arguments_count(search_term),
            'accounts_count': self.get_accounts_count(search_term)
        }

        return Response(count)

    def get_moogts_count(self, search_term):
        queryset = Moogt.objects.get_all_moogts().filter_using_search_term(search_term)
        if self.request.user.is_authenticated:
            queryset = queryset.filter_moogts_by_blocked_users(
                self.request.user)
        return queryset.count()

    def get_views_count(self, search_term):
        queryset = View.objects.filter_using_search_term(search_term)
        if self.request.user.is_authenticated:
            queryset = queryset.filter_views_by_blocked_users(
                self.request.user)
        return queryset.count()

    def get_polls_count(self, search_term):
        queryset = Poll.objects.filter_using_search_term(search_term)
        if self.request.user.is_authenticated:
            queryset = queryset.filter_poll_by_blocked_user(self.request.user)
        return queryset.count()

    def get_arguments_count(self, search_term):
        queryset = Argument.objects.filter_using_search_term(search_term)
        return queryset.count()

    def get_accounts_count(self, search_term):
        queryset = MoogtMedaUser.objects.exclude(
            pk=self.request.user.pk).filter_using_search_term(search_term)

        if self.request.user.is_authenticated:
            queryset = queryset.filter_blocked_users(self.request.user)

        return queryset.count()


class TelegramOptInApiView(generics.GenericAPIView):
    serializer_class = TelegramChatToUserSerializer

    def post(self, request, *args, **kwargs):
        chat_id = request.query_params.get('cid', None)

        if chat_id:
            telegram = TelegramChatToUser.objects.get_or_create(
                user=request.user, chat_id=chat_id)[0]
            bot.sendMessage(
                telegram.chat_id, 'You have successfully Opted in Telegram notifications')
        else:
            return Response({"err": "You have not provided chat_id of user to opt-in to"},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': True}, status=status.HTTP_200_OK)


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    authentication_classes = []
    client_class = OAuth2Client


class ObtainJSONWebTokenFromFirebaseToken(ObtainJSONWebToken):
    """
    API View that receives a POST with firebase auth token.

    Returns a JSON Web Token that can be used for authenticated requests.
    """
    serializer_class = FirebaseJSONWebTokenSerializer


obtain_token_from_firebase_token = ObtainJSONWebTokenFromFirebaseToken.as_view()
