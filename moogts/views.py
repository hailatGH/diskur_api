import json
from urllib import request

import django.core
import rest_framework.exceptions
from django.db import transaction
from django.db.models import Q, Count, OuterRef, Subquery, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
# Create your views here.
from rest_framework import generics, permissions, filters, status, mixins
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin

from api.enums import ShareProvider, ReactionType
from api.mixins import ReportMixin, TrendingMixin, UpdatePublicityMixin, ShareMixin, ActivityActionValidationMixin, \
    ActivityCreationValidationMixin, ViewArgumentReactionMixin
from api.pagination import SmallResultsSetPagination
from api.signals import reaction_was_made
from arguments.models import Argument
from arguments.serializers import ArgumentSerializer
from chat.models import MessageSummary
from invitations.models import Invitation
from meda.enums import ModeratorInvititaionStatus, MoogtEndStatus, InvitationStatus, ActivityStatus, ArgumentType
from invitations.models import ModeratorInvitation
from meda.models import AbstractActivityAction
from moogts.utils import quit_moogts, get_awaited_user
from views.models import View
from moogts.enums import MiniSuggestionState, MoogtActivityType, DonationLevel
from moogts.extensions import BasicMoogtExtensions
from moogts.models import Moogt, MoogtMiniSuggestion, MoogtBanner, MoogtActivity, Donation, ReadBy, \
    MoogtStatus, MoogtActivityBundle
from moogts.serializers import MoogtReportSerializer, MoogtSerializer, MoogtMiniSuggestionSerializer, MoogtBannerSerializer, \
    MoogtActivitySerializer, DonationSerializer, MoogtNotificationSerializer, MoogtStatusSerializer
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from users import dynamic_preferences_registry as dynamic_prefs
from users.models import MoogtMedaUser, Activity, ActivityType, CreditPoint
from users.serializers import MoogtMedaUserSerializer


class MoogtListView(SerializerExtensionsAPIViewMixin,
                    TrendingMixin,
                    generics.ListAPIView,
                    BasicMoogtExtensions):
    serializer_class = MoogtSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['resolution', 'arguments__argument']
    pagination_class = SmallResultsSetPagination
    extensions_auto_optimize = True

    def get_queryset(self):
        queryset = Moogt.objects.get_all_moogts()

        if self.request.user.is_authenticated:
            queryset = queryset.filter_moogts_by_blocked_users(
                self.request.user)

        # Check if the request has trending query param. If so get trending moogts.
        is_trending = json.loads(
            self.request.query_params.get('trending', 'false'))

        premiering_only = json.loads(
            self.request.query_params.get('premiering_only', 'false'))

        if premiering_only:
            queryset = queryset.get_premiering_moogts()
        else:
            queryset = queryset.get_non_premiering_moogts()

        if is_trending:
            return self.get_overall_score_trending_factor_queryset(queryset)

        # Check if the request has feed_only param.
        feed_only = json.loads(
            self.request.query_params.get('feed_only', 'false'))
        if self.request.user.is_authenticated and feed_only:
            user = get_object_or_404(MoogtMedaUser, pk=self.request.user.id)
            following_ids = user.following.values_list('id', flat=True)
            queryset = queryset.filter(proposition_id__in=following_ids)

        return queryset.order_by('-updated_at')

    def get_serializer(self, *args, **kwargs):
        return super().get_serializer(*args, **kwargs)


class MoogtCreateView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MoogtSerializer
    extensions_expand = ['tags']

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        moogt_serializer = self.get_serializer(data=request.data)

        if not moogt_serializer.is_valid():
            raise rest_framework.exceptions.ValidationError(
                moogt_serializer.errors)

        banner = None
        if request.data.get('banner_id'):
            banner = get_object_or_404(
                MoogtBanner, pk=request.data.get('banner_id'))

        proposition = request.data.get('second_invitee_id')
        if not proposition:
            proposition = request.user

        moogt = moogt_serializer.save(
            proposition=get_object_or_404(MoogtMedaUser, pk=proposition), banner=banner)

        email_pref_key = f'{dynamic_prefs.EmailNotificationForInvitationEnabled.section}__' \
                         f'{dynamic_prefs.EmailNotificationForInvitationEnabled.name}'

        invitee_id = request.data.get('invitee_id')
        if invitee_id:

            invitee = get_object_or_404(MoogtMedaUser, pk=invitee_id)

            invitation = Invitation(
                moogt=moogt, inviter=request.user, invitee=invitee)

            try:
                invitation.validate()
            except django.core.exceptions.ValidationError as err:
                raise rest_framework.exceptions.ValidationError(err)

            invitation.save()
            moogt.set_opposition(invitee)

        moderator_id = request.data.get('moderator_id')
        if moderator_id and moderator_id != request.user.id:
            moderator = get_object_or_404(MoogtMedaUser, pk=moderator_id)

            moderator_invitation = ModeratorInvitation(
                moderator=moderator, invitation=invitation)

            #  make sure it's a different user than the proposition/opposition.
            # try:
            #     moderator_invitation.validate(
            #         inviter=request.user, invitee=invitee)
            # except django.core.exceptions.ValidationError as err:
            #     raise rest_framework.exceptions.ValidationError(err)

            moderator_invitation.save()
        elif proposition & proposition != request.user.id:

            moderator = get_object_or_404(MoogtMedaUser, pk=moderator_id)

            # moderator_invitation = ModeratorInvitation(
            #     moderator=moderator, invitation=invitation)

            # moderator_invitation.set_status(
            #     ModeratorInvititaionStatus.accepted())

            #  make sure it's a different user than the proposition/opposition.
            # try:
            #     moderator_invitation.validate(
            #         inviter=request.user, invitee=invitee)
            # except django.core.exceptions.ValidationError as err:
            #     raise rest_framework.exceptions.ValidationError(err)

            # moderator_invitation.save()
            moogt.set_moderator(self.request.user)
            moogt.save()
            secondInvitee = get_object_or_404(MoogtMedaUser, pk=proposition)
            invitation = Invitation(
                moogt=moogt, inviter=request.user, invitee=secondInvitee)

            try:
                invitation.validate()
            except django.core.exceptions.ValidationError as err:
                raise rest_framework.exceptions.ValidationError(err)

            invitation.save()

        moogt = get_object_or_404(Moogt, pk=moogt.id)
        self.extensions_expand = BasicMoogtExtensions.extensions_expand

        moogt.followers.add(request.user)
        request.user.last_opened_following_moogt = moogt
        Activity.record_activity(request.user.profile,
                                 ActivityType.follow_moogt.name, moogt.id)

        self.create_moogt_read_by(moogt)

        return Response(data=self.get_serializer(moogt).data, status=status.HTTP_201_CREATED)

    def create_moogt_read_by(self, moogt):
        queryset = self.request.user.read_moogts.filter(moogt=moogt)
        if not queryset.exists():
            return ReadBy.objects.create(user=self.request.user, moogt=moogt)

        read_by = queryset.first()
        read_by.latest_read_at = timezone.now()
        read_by.save()

        return read_by

    def get_extensions_mixin_context(self):
        context = super(MoogtCreateView, self).get_extensions_mixin_context()
        exclude = []
        if 'tags' not in self.request.data:
            exclude += ['tags']
        context['exclude'] = set(exclude)
        return context


class MoogtDetailView(SerializerExtensionsAPIViewMixin, generics.RetrieveAPIView,
                      BasicMoogtExtensions):
    serializer_class = MoogtSerializer
    # permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    extensions_auto_optimize = True

    # TODO fix the get function
    def get(self, request, *args, **kwargs):
        moogt: Moogt = self.get_object()

        if moogt.is_removed:
            return Response(status=status.HTTP_204_NO_CONTENT)

        moogt.func_update_premiering_field()
        moogt.func_create_moogt_started_status()
        moogt.func_skip_expired_turns()
        moogt.func_expire_moogt_activities()
        moogt.func_end_moogt()

        self.update_stats(request.user, moogt)

        return super().get(request, *args, **kwargs)

    def get_object(self):
        moogt = get_object_or_404(Moogt.all_objects, pk=self.kwargs.get('pk'))
        if not moogt.is_removed:
            return get_object_or_404(Moogt, pk=self.kwargs.get('pk'))
        return moogt

    @staticmethod
    def update_stats(user, moogt):
        # TODO: Do something smarter. Right now, anyone who is not
        # a moogter can spam the view count.
        # Maybe only allow one view per session? Including anonymous users?
        # Or just allow one per user?
        if user.is_authenticated:
            user = MoogtMedaUser.objects.get(pk=user.id)
            if user == moogt.opposition or user == moogt.proposition:
                user.last_opened_moogt = moogt

            if user in moogt.followers.all():
                user.last_opened_following_moogt = moogt
            user.save()

        if user.is_authenticated and (user != moogt.get_proposition()) and (user != moogt.get_opposition()):
            stats = moogt.stats
            stats.view_count += 1
            stats.save()

            try:
                activity = Activity()
                activity.profile = user.profile
                activity.type = ActivityType.view_moogt.name
                activity.object_id = moogt.id
                activity.save()

                CreditPoint.create(
                    activity, ActivityType.view_proposition_moogt.name, moogt.get_proposition().profile)

                if moogt.get_opposition() is not None:
                    CreditPoint.create(
                        activity, ActivityType.view_opposition_moogt.name, moogt.get_opposition().profile)
            except:
                pass

    def get_queryset(self):
        return Moogt.objects.all()

    def get_extensions_mixin_context(self):
        context = super(MoogtDetailView, self).get_extensions_mixin_context()
        exclude = []

        moogt = self.get_object()
        if not moogt.func_is_participant(self.request.user):
            exclude = ['total_donations', 'your_donations']

        context['exclude'] = set(exclude)
        return context


class FollowingMoogtListApiView(SerializerExtensionsAPIViewMixin,
                                generics.ListAPIView):
    serializer_class = MoogtSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        sub = self.request.user.read_moogts.filter(
            moogt=OuterRef('pk')).values('latest_read_at')
        queryset = self.request.user \
            .following_moogts \
            .annotate(latest_read_at=Subquery(sub),
                      unread_count=Count('arguments',
                                         filter=(Q(arguments__created_at__gt=F('latest_read_at'))))) \
            .order_by('-unread_count', '-latest_argument_added_at')

        queryset = queryset.filter(
            ~Q(opposition=self.request.user) & ~Q(proposition=self.request.user))

        queryset = queryset.filter_moogts_by_blocked_users(self.request.user)

        return queryset


class AcceptMoogtView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView):
    http_method_names = ['post']
    serializer_class = MoogtSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk', None)
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        if (moogt.get_opposition() is not None) or (request.user == moogt.get_proposition()):
            raise rest_framework.exceptions.ValidationError(
                'Invalid attempt to accept moogt.')

        moogt.func_start(request.user)

        moogt_serializer = self.get_serializer(moogt)

        moogt.followers.add(request.user)
        request.user.last_opened_following_moogt = moogt
        Activity.record_activity(request.user.profile,
                                 ActivityType.follow_moogt.name, moogt.id)

        self.create_moogt_read_by(moogt)

        return Response(moogt_serializer.data, status=status.HTTP_200_OK)

    def create_moogt_read_by(self, moogt):
        queryset = self.request.user.read_moogts.filter(moogt=moogt)
        if not queryset.exists():
            return ReadBy.objects.create(user=self.request.user, moogt=moogt)

        read_by = queryset.first()
        read_by.latest_read_at = timezone.now()
        read_by.save()

        return read_by


class UpdateMoogtPublicityStatusView(UpdatePublicityMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MoogtSerializer

    def post(self, request, *args, **kwargs):
        visibility = request.data.get("visibility")
        moogt_id = request.data.get("moogt_id")
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        moogt = self.update_publicity(moogt, visibility)
        return Response(self.get_serializer(moogt).data, status.HTTP_200_OK)


class FollowMoogtAPIView(generics.GenericAPIView, BasicMoogtExtensions):
    serializer_class = MoogtSerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        self.validate(moogt, request.user)
        followed = False

        if request.user in moogt.followers.all():
            moogt.followers.remove(request.user)
            request.user.last_opened_following_moogt = None
            Notification.objects.remove_notification(
                moogt, request.user, NOTIFICATION_TYPES.moogt_follow)
        else:
            followed = True
            moogt.followers.add(request.user)
            request.user.last_opened_following_moogt = moogt
            Activity.record_activity(
                request.user.profile, ActivityType.follow_moogt.name, moogt.id)

            self.create_moogt_read_by(moogt)

        request.user.save()
        if followed:
            notify.send(recipient=MoogtMedaUser.objects.filter(id=moogt.opposition.pk) |
                        MoogtMedaUser.objects.filter(id=moogt.proposition.pk),
                        sender=request.user,
                        verb="followed",
                        send_email=False,
                        type=NOTIFICATION_TYPES.moogt_follow,
                        send_telegram=True,
                        target=moogt,
                        data={'moogt': MoogtNotificationSerializer(
                            moogt).data},
                        push_notification_title=f'{request.user} Followed your Moogt',
                        push_notification_description=f'{request.user} followed your Moogt, "{moogt}"')

        reaction_was_made.send(__class__, obj=moogt)
        return Response(self.get_serializer(moogt).data, status=status.HTTP_200_OK)

    def create_moogt_read_by(self, moogt):
        queryset = self.request.user.read_moogts.filter(moogt=moogt)
        if not queryset.exists():
            return ReadBy.objects.create(user=self.request.user, moogt=moogt)

        read_by = queryset.first()
        read_by.latest_read_at = timezone.now()
        read_by.save()

        return read_by

    @staticmethod
    def validate(moogt, user):
        if moogt.get_proposition() == user or moogt.get_opposition() == user:
            raise rest_framework.exceptions.ValidationError(
                "You cannot follow your own moogt.")

        blocked_moogters_count = user.blockings.filter(Q(blocked_user=moogt.get_proposition()) | Q(
            blocked_user=moogt.get_opposition()) | Q(blocked_user=moogt.get_moderator())
        ).count()

        should_raise_exception = True if moogt.get_moderator(
        ) and blocked_moogters_count == 3 or moogt.get_moderator() is None and blocked_moogters_count == 2 else False

        if should_raise_exception:
            raise rest_framework.exceptions.ValidationError(
                'You cannot follow moogts while you have blocked everyone in the moogt.'
            )

        blockers_count = user.blockers.filter(Q(user=moogt.get_proposition()) | Q(
            user=moogt.get_opposition()) | Q(user=moogt.get_moderator())).count()

        should_raise_exception = True if moogt.get_moderator(
        ) and blockers_count == 3 or moogt.get_moderator() is None and blockers_count == 2 else False

        if should_raise_exception:
            raise rest_framework.exceptions.ValidationError(
                'You cannot follow moogts while you are blocked by every participant.'
            )


class MyMoogtListApiView(SerializerExtensionsAPIViewMixin, generics.ListAPIView, BasicMoogtExtensions):
    serializer_class = MoogtSerializer
    permission_classes = [permissions.IsAuthenticated]

    extensions_auto_optimize = True

    def get_queryset(self):
        started_moogts = Moogt.objects.get_all_moogts().get_user_moogts(self.request.user)
        queryset = started_moogts.filter(
            has_ended=False).order_by('-latest_argument_added_at')
        return queryset


class LastOpenedMoogtApiView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView, BasicMoogtExtensions):
    serializer_class = MoogtSerializer

    extensions_auto_optimize = True

    def get(self, request, *args, **kwargs):
        user = MoogtMedaUser.objects.get(pk=request.user.id)
        is_following = json.loads(
            self.request.query_params.get('following', 'false'))
        if is_following:
            moogt = user.last_opened_following_moogt
        else:
            moogt = user.last_opened_moogt

        if moogt is None:
            return Response(None)

        moogt = get_object_or_404(Moogt, pk=moogt.id)

        return Response(self.get_serializer(moogt).data, status.HTTP_200_OK)


class GetBundleActivitiesApiView(SerializerExtensionsAPIViewMixin, generics.ListAPIView):
    serializer_class = MoogtActivitySerializer
    pagination_class = SmallResultsSetPagination
    extensions_expand = ['react_to']

    def get_queryset(self):
        pk = self.kwargs.get('pk')
        bundle = get_object_or_404(MoogtActivityBundle, pk=pk)
        return MoogtActivity.objects.filter(bundle=bundle).order_by('-updated_at', '-created_at')


class EndMoogtView(generics.GenericAPIView, BasicMoogtExtensions):
    serializer_class = MoogtSerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        # Validate it's a moogt participant that is trying to end this moogt.
        if request.user not in [moogt.get_proposition(), moogt.get_opposition(), moogt.get_moderator()]:
            raise ValidationError('Non-participant cannot end this moogt')

        if request.data.get('status') == MoogtEndStatus.concede():
            moogt.set_end_requested(True)
            moogt.set_end_requested_by_proposition(
                request.user == moogt.get_proposition())
            moogt.set_end_request_status(MoogtEndStatus.concede())
            moogt.set_has_ended(True)
            moogt.save()

        return Response(self.get_serializer(moogt).data, status=status.HTTP_200_OK)


class ShareMoogt(ShareMixin,
                 generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        share_count = self.share(request)
        moogt.stats.func_update_share_count(
            ShareProvider.FACEBOOK.name, share_count)

        return Response(share_count, status=status.HTTP_200_OK)


class MoogtSuggestionApiView(SerializerExtensionsAPIViewMixin, generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MoogtMiniSuggestionSerializer

    def post(self, request, *args, **kwargs):
        moogt_id = request.data.get('moogt', None)
        if not moogt_id:
            raise ValidationError('A moogt id must be provided.')

        moogt: Moogt = get_object_or_404(Moogt, pk=moogt_id)

        changes = request.data.get('changes', [])
        for change in changes:
            if 'max_duration' not in change and 'idle_timeout_duration' not in change and len(change.items()) > 1:
                raise ValidationError()

            change_column = list(change.keys())[0]
            lookup = "%s__isnull" % change_column
            if moogt.mini_suggestions.filter(**{lookup: False}, user=request.user,
                                             state=MiniSuggestionState.PENDING.value).exists():
                raise ValidationError(
                    'Pending %s minisuggestion already exists' % change_column)

            moderator_id = change.pop(
                'moderator') if 'moderator' in change else None
            moderator = None
            if moderator_id:
                moderator = get_object_or_404(MoogtMedaUser, pk=moderator_id)

            banner_id = change.pop('banner') if 'banner' in change else None
            banner = None
            if banner_id:
                banner = get_object_or_404(MoogtBanner, pk=banner_id)

            if 'remove_banner' in change and moogt.banner is None:
                raise ValidationError("Moogt has no banner to be removed")

            if 'tags' in change:
                self.extensions_expand = {'tags'}

            parent_suggestion = self.get_parent_suggestion(
                moogt, change.keys())
            serializer = self.get_serializer(data=change)
            if serializer.is_valid(raise_exception=True):
                suggestion = serializer.save(
                    moogt=moogt, moderator=moderator, banner=banner)
                if parent_suggestion:
                    parent_suggestion.state = MiniSuggestionState.EDITED.value
                    parent_suggestion.suggested_child = suggestion
                    parent_suggestion.message.summaries.create(actor=self.request.user,
                                                               verb=MessageSummary.VERBS.EDIT.value)
                    parent_suggestion.save()

        invitation = moogt.invitations.order_by('-created_at').first()
        if invitation and invitation.get_status() == InvitationStatus.pending():
            invitation.set_status(InvitationStatus.revised())
            invitation.save()
        return Response(status=status.HTTP_201_CREATED)

    def get_parent_suggestion(self, moogt, keys):
        lookup = {f'{key}__isnull': False for key in keys}
        parent_suggestion = MoogtMiniSuggestion.objects.filter(**lookup,
                                                               state=MiniSuggestionState.PENDING.value,
                                                               moogt=moogt
                                                               ).exclude(user=self.request.user).first()

        return parent_suggestion


class MoogtSuggestionActionApiView(SerializerExtensionsAPIViewMixin,
                                   generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MoogtMiniSuggestionSerializer

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        suggestion_id = request.data.get('suggestion_id')
        action = request.data.get('action', None)

        if action is None:
            ValidationError("No action was provided")

        suggestion: MoogtMiniSuggestion = get_object_or_404(
            MoogtMiniSuggestion, pk=suggestion_id)
        if action == MiniSuggestionState.APPROVED.value:
            suggestion.approve(self.request.user)
            suggestion.message.summaries.create(
                verb=MessageSummary.VERBS.APPROVE.value, actor=request.user)

        elif action == MiniSuggestionState.DISAPPROVED.value:
            suggestion.disapprove()
            suggestion.message.summaries.create(
                verb=MessageSummary.VERBS.DECLINE.value, actor=request.user)

        elif action == MiniSuggestionState.CANCEL.value:
            suggestion.cancel()
            suggestion.message.summaries.create(
                verb=MessageSummary.VERBS.CANCEL.value, actor=request.user)

        return Response(self.get_serializer(suggestion).data, status=status.HTTP_200_OK)


class MoogtSuggestionListApiView(SerializerExtensionsAPIViewMixin,
                                 generics.ListAPIView):
    serializer_class = MoogtMiniSuggestionSerializer

    def get_queryset(self):
        pk = self.kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=pk)
        return moogt.mini_suggestions.all()


class UploadBannerApiView(generics.CreateAPIView):
    serializer_class = MoogtBannerSerializer


class HasLiveMoogtsView(generics.GenericAPIView):
    """
    Check if the user has live moogts.
    """
    serializer_class = MoogtMedaUserSerializer

    def get(self, request, *args, **kwargs):
        for moogt in request.user.opposition_moogts.all():
            if moogt.func_has_started() and not moogt.func_has_expired():
                return Response({"success": True}, status=status.HTTP_200_OK)

        for moogt in request.user.proposition_moogts.all():
            if moogt.func_has_started() and not moogt.func_has_expired():
                return Response({"success": True}, status=status.HTTP_200_OK)

        return Response({"success": False}, status=status.HTTP_200_OK)


class UpdateMoogtApiView(generics.UpdateAPIView):
    serializer_class = MoogtSerializer
    queryset = Moogt.objects.all()

    def post(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class UpdateAllSuggestionsApiView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        moogt = get_object_or_404(Moogt, pk=kwargs.get('pk'))
        mini_suggestions = moogt.mini_suggestions.filter(
            state=MiniSuggestionState.PENDING.value)
        # This means there are no mini suggestions for this moogt. Therefore
        # throw a ValidationError.
        if mini_suggestions.count() == 0:
            raise ValidationError('There are no pending mini suggestions')

        action = request.data.get('action')
        if action == MiniSuggestionState.APPROVED.value:
            mini_suggestions = mini_suggestions.exclude(user=request.user)

            if mini_suggestions.count() == 0:
                raise ValidationError(
                    'There are no pending suggestions you can approve.')

            for mini_suggestion in mini_suggestions:
                mini_suggestion.approve(self.request.user)
            return Response('Successfully approved all suggestions.')

        if action == MiniSuggestionState.CANCEL.value:
            mini_suggestions = mini_suggestions.filter(user=request.user)
            for mini_suggestion in mini_suggestions:
                mini_suggestion.cancel()
            return Response('Successfully cancelled all suggestions.')

        raise ValidationError()


class MakeCardRequestApiView(ActivityCreationValidationMixin,
                             generics.GenericAPIView,
                             mixins.CreateModelMixin):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        self.moogt: Moogt = get_object_or_404(Moogt, pk=moogt_id)
        self.verb = "requested for an extra card"
        self.push_notification_title = f'{self.request.user} requested for an Extra Turn'
        self.push_notification_description = f'{self.request.user} requested for an extra turn in the Moogt, "{self.moogt}"'

        self.validate(self.moogt, MoogtActivityType.CARD_REQUEST.value)

        if request.user == self.moogt.get_moderator():
            raise rest_framework.exceptions.PermissionDenied(
                'Moderators are not allowed to perform this action.')

        if self.moogt.func_is_current_turn(request.user):
            raise rest_framework.exceptions.PermissionDenied(
                'You are not allowed to perform this action.')

        request.data['moogt'] = self.moogt
        request.data['type'] = MoogtActivityType.CARD_REQUEST.value
        request.data['actor'] = self.moogt.get_opponent(request.user)
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        self.perform_create_with_notifications_moogt(serializer)


class CardRequestActionApiView(ActivityActionValidationMixin,
                               generics.GenericAPIView):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = kwargs.get('pk')
        moogt_activity = get_object_or_404(MoogtActivity, pk=activity_id)
        moogt: Moogt = moogt_activity.moogt
        send_notification = True
        verb = 'approved card request'

        if moogt_activity.type != MoogtActivityType.CARD_REQUEST.name:
            raise ValidationError(
                "This endpoint is to take action only on Extra Card requests")

        activity_status = self.validate(moogt_activity)

        if activity_status == ActivityStatus.ACCEPTED.value:

            self.create_or_update_bundle(moogt, moogt_activity)
            argument = Argument(moogt=moogt,
                                type=ArgumentType.WAIVED.name)
            if moogt.get_next_turn_proposition():
                argument.set_user(moogt.get_proposition())
            else:
                argument.set_user(moogt.get_opposition())
            argument.save()
            moogt.func_update_moogt(self.request.user, 'continue')

            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
            moogt_activity.save()

            self.push_notification_title = f'{self.request.user} approved request for an Extra Turn'
            self.push_notification_description = f'{self.request.user} approved your request for an Extra Turn/Card in the Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.DECLINED.value:

            if moogt.get_moderator():
                if moogt_activity.status == ActivityStatus.PENDING.value:
                    self.create_or_update_bundle(moogt, moogt_activity)

                    moogt_activity.status = ActivityStatus.WAITING.value
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    moogt_activity.save()

                    self.push_notification_title = f'{self.request.user} Declined request for an Extra Turn - Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'
                    self.push_notification_description = f'{self.request.user} declined your request for an Extra Turn/Card in the Moogt, "{moogt}" Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)} to also vote.'

                elif moogt_activity.status == ActivityStatus.WAITING.value:
                    moogt_activity.status = activity_status
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    moogt_activity.save()

                    self.create_or_update_bundle(moogt, moogt_activity)

                    self.push_notification_title = f'{self.request.user} Declined request for an Extra Turn'
                    self.push_notification_description = f'{self.request.user} declined your request for an Extra Turn/Card in the Moogt, "{moogt}"'
            else:
                self.create_or_update_bundle(
                    moogt_activity.moogt, moogt_activity)

                moogt_activity.status = activity_status
                moogt_activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                moogt_activity.save()

                self.push_notification_title = f'{self.request.user} Declined request for an Extra Turn'
                self.push_notification_description = f'{self.request.user} declined your request for an Extra Turn/Card in the Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.CANCELLED.value:
            send_notification = False
            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            moogt_activity.save()

        if send_notification:
            self.send_notification(moogt_activity.user,
                                   moogt_activity.moogt,
                                   verb,
                                   NOTIFICATION_TYPES.moogt_request_resolved,
                                   data={'moogt': MoogtNotificationSerializer(moogt_activity.moogt).data,
                                         'activity': MoogtActivitySerializer(moogt_activity).data},
                                   push_notification_title=self.push_notification_title,
                                   push_notification_description=self.push_notification_description

                                   )

        return Response(self.get_serializer(moogt_activity).data)


class MakeEndMoogtRequestApiView(ActivityCreationValidationMixin,
                                 generics.GenericAPIView,
                                 mixins.CreateModelMixin):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        self.moogt: Moogt = get_object_or_404(Moogt, pk=moogt_id)
        self.verb = "requested to end"

        if self.request.user == self.moogt.get_moderator():
            self.push_notification_title = f'{self.request.user} requested to End Moogt as Moderator'
            self.push_notification_description = f'{self.request.user} requested to End the Moogt as a Moderator, "{self.moogt}"'
        else:
            self.push_notification_title = f'{self.request.user} requested to End Moogt'
            self.push_notification_description = f'{self.request.user} requested to End the Moogt, "{self.moogt}"'

        self.validate(self.moogt, MoogtActivityType.END_REQUEST.value)

        self.moogt.set_end_requested(True)
        self.moogt.set_end_requested_by_proposition(
            request.user == self.moogt.get_proposition())
        self.moogt.save()

        request.data['moogt'] = self.moogt
        request.data['type'] = MoogtActivityType.END_REQUEST.value
        request.data['actor'] = self.moogt.get_opponent(request.user)
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        self.perform_create_with_notifications_moogt(serializer)


class EndMoogtRequestActionApiView(ActivityActionValidationMixin,
                                   generics.GenericAPIView):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = kwargs.get('pk')
        moogt_activity = get_object_or_404(MoogtActivity, pk=activity_id)
        moogt: Moogt = moogt_activity.moogt

        if moogt_activity.type != MoogtActivityType.END_REQUEST.name:
            raise ValidationError(
                "This endpoint is to take action only on End Moogt requests")

        activity_status = self.validate(moogt_activity)
        send_notification = True
        verb = "ended"

        if activity_status == ActivityStatus.ACCEPTED.value:
            moogt: Moogt = moogt_activity.moogt
            moogt.set_has_ended(True)
            moogt.set_is_paused(False)
            moogt.set_paused_at(None)
            moogt.set_paused_by(None)
            moogt.save()

            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
            moogt_activity.save()

            self.create_or_update_bundle(moogt, moogt_activity)

            moogt_ended = MoogtStatus(
                moogt=moogt, status=MoogtStatus.STATUS.ended)
            moogt_ended.save()

            self.push_notification_title = f'{self.request.user} Approved request to End Moogt'
            self.push_notification_description = f'{self.request.user} approved your request to End Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.DECLINED.value:
            if moogt.get_moderator():
                if moogt_activity.status == ActivityStatus.PENDING.value:
                    self.create_or_update_bundle(moogt, moogt_activity)

                    moogt_activity.status = ActivityStatus.WAITING.value
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    moogt_activity.save()

                    self.push_notification_title = f'{self.request.user} Declined request to End Moogt - Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'
                    self.push_notification_description = f'{self.request.user} declined your request to End Moogt, "{moogt}" Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'

                elif moogt_activity.status == ActivityStatus.WAITING.value:
                    moogt_activity.status = activity_status
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    moogt_activity.save()

                    self.create_or_update_bundle(moogt, moogt_activity)

                    self.push_notification_title = f'{self.request.user} Declined request to End Moogt'
                self.push_notification_description = f'{self.request.user} declined your request to End Moogt, "{moogt}"'

            else:
                verb = "declined"
                self.create_or_update_bundle(
                    moogt_activity.moogt, moogt_activity)

                moogt_activity.status = activity_status
                moogt_activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                moogt_activity.save()

                self.push_notification_title = f'{self.request.user} Declined request to End Moogt'
                self.push_notification_description = f'{self.request.user} declined your request to End Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.CANCELLED.value:
            send_notification = False
            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            moogt_activity.save()

        if send_notification:
            self.send_notification(moogt_activity.user,
                                   moogt_activity.moogt,
                                   verb,
                                   NOTIFICATION_TYPES.moogt_request_resolved,
                                   data={'moogt': MoogtNotificationSerializer(moogt_activity.moogt).data,
                                         'activity': MoogtActivitySerializer(moogt_activity).data},
                                   push_notification_title=self.push_notification_title,
                                   push_notification_description=self.push_notification_description
                                   )

        return Response(self.get_serializer(moogt_activity).data)


class MakePauseMoogtRequestApiView(ActivityCreationValidationMixin,
                                   generics.GenericAPIView,
                                   mixins.CreateModelMixin):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        self.moogt: Moogt = get_object_or_404(Moogt, pk=moogt_id)
        self.verb = "requested to pause"

        if self.request.user == self.moogt.get_moderator():
            self.push_notification_title = f'{self.request.user} requested to Pause Moogt as Moderator'
            self.push_notification_description = f'{self.request.user} requested to Pause the Moogt as a Moderator, "{self.moogt}"'
        else:
            self.push_notification_title = f'{self.request.user} requested to Pause Moogt'
            self.push_notification_description = f'{self.request.user} requested to Pause the Moogt, "{self.moogt}"'

        self.validate(self.moogt, MoogtActivityType.PAUSE_REQUEST.value)
        request.data['moogt'] = self.moogt
        request.data['type'] = MoogtActivityType.PAUSE_REQUEST.value
        request.data['actor'] = self.moogt.get_opponent(request.user)

        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        self.perform_create_with_notifications_moogt(serializer)


class PauseMoogtRequestActionApiView(ActivityActionValidationMixin,
                                     generics.GenericAPIView):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = kwargs.get('pk')
        moogt_activity = get_object_or_404(MoogtActivity, pk=activity_id)
        send_notification = True
        verb = "paused"
        moogt: Moogt = moogt_activity.moogt

        if moogt_activity.type != MoogtActivityType.PAUSE_REQUEST.name:
            raise ValidationError(
                "This endpoint is to take action only on Pause Moogt requests")

        activity_status = self.validate(moogt_activity)

        if activity_status == ActivityStatus.ACCEPTED.value:
            moogt_activity.status = activity_status
            moogt.func_pause_moogt(request.user, paused_at=timezone.now())
            moogt.save()

            self.create_or_update_bundle(moogt, moogt_activity)

            moogt_paused = MoogtStatus(
                moogt=moogt, status=MoogtStatus.STATUS.paused)
            moogt_paused.save()

            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
            moogt_activity.save()

            self.push_notification_title = f'{self.request.user} Approved request to Pause Moogt'
            self.push_notification_description = f'{self.request.user} approved your request to Pause the Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.DECLINED.value:
            if moogt.get_moderator():
                if moogt_activity.status == ActivityStatus.PENDING.value:
                    moogt_activity.status = ActivityStatus.WAITING.value
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    moogt_activity.save()
                    self.create_or_update_bundle(moogt, moogt_activity)
                    self.push_notification_title = f'{self.request.user} declined request to Pause Moogt - Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'
                    self.push_notification_description = f'{self.request.user} declined request to pause the Moogt, "{moogt}" Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)} to also vote.'

                elif moogt_activity.status == ActivityStatus.WAITING.value:
                    moogt_activity.status = activity_status
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    moogt_activity.save()
                    self.create_or_update_bundle(moogt, moogt_activity)

                    self.push_notification_title = f'{self.request.user} Declined request to Pause Moogt'
                    self.push_notification_description = f'{self.request.user} declined your request to Pause the Moogt, "{moogt}"'

            else:
                self.create_or_update_bundle(
                    moogt_activity.moogt, moogt_activity)
                moogt_activity.status = activity_status
                moogt_activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                moogt_activity.save()

                self.push_notification_title = f'{self.request.user} Declined request to Pause Moogt'
                self.push_notification_description = f'{self.request.user} declined your request to Pause the Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.CANCELLED.value:
            send_notification = False

            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            moogt_activity.save()

        if send_notification:
            self.send_notification(moogt_activity.user,
                                   moogt_activity.moogt,
                                   verb,
                                   NOTIFICATION_TYPES.moogt_request_resolved,
                                   data={'moogt': MoogtNotificationSerializer(moogt_activity.moogt).data,
                                         'activity': MoogtActivitySerializer(moogt_activity).data},
                                   push_notification_title=self.push_notification_title,
                                   push_notification_description=self.push_notification_description
                                   )

        return Response(self.get_serializer(moogt_activity).data)


class MakeResumeMoogtRequestApiView(ActivityCreationValidationMixin,
                                    generics.GenericAPIView,
                                    mixins.CreateModelMixin):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        self.moogt: Moogt = get_object_or_404(Moogt, pk=moogt_id)
        self.verb = "requested to resume"

        self.push_notification_title = f'{self.request.user} requested to Resume Moogt'
        self.push_notification_description = f'{self.request.user} requested to Resume the Moogt, "{self.moogt}"'

        self.validate(self.moogt, MoogtActivityType.RESUME_REQUEST.value)

        if not self.moogt.get_is_paused():
            raise ValidationError('The moogt is not paused.')

        request.data['moogt'] = self.moogt
        request.data['type'] = MoogtActivityType.RESUME_REQUEST.value
        request.data['actor'] = self.moogt.get_opponent(request.user)
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        self.perform_create_with_notifications_moogt(serializer)


class ResumeMoogtRequestActionApiView(ActivityActionValidationMixin,
                                      generics.GenericAPIView):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = kwargs.get('pk')
        moogt_activity = get_object_or_404(MoogtActivity, pk=activity_id)
        moogt: Moogt = moogt_activity.moogt

        if moogt_activity.type != MoogtActivityType.RESUME_REQUEST.name:
            raise ValidationError(
                "This endpoint is to take action only on Resume Moogt requests")

        activity_status = self.validate(moogt_activity)
        verb = "resumed"
        send_notification = True

        if activity_status == ActivityStatus.ACCEPTED.value:

            if moogt.func_resume_moogt(request.user):
                moogt.save()

                self.create_or_update_bundle(moogt, moogt_activity)

                moogt_resumed = MoogtStatus(
                    moogt=moogt, status=MoogtStatus.STATUS.resumed)
                moogt_resumed.save()

                moogt_activity.status = activity_status
                moogt_activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
                moogt_activity.save()

                self.push_notification_title = f'{self.request.user} Approved request to Resume Moogt'
                self.push_notification_description = f'{self.request.user} approved your request to Resume the Moogt, "{moogt}"'

            else:
                raise ValidationError('The moogt is not paused.')

        elif activity_status == ActivityStatus.DECLINED.value:

            if moogt.get_moderator():
                if moogt_activity.status == ActivityStatus.PENDING.value:
                    self.create_or_update_bundle(moogt, moogt_activity)

                    moogt_activity.status = ActivityStatus.WAITING.value
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    moogt_activity.save()

                    self.push_notification_title = f'{self.request.user} Declined request to Resume Moogt - Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'
                    self.push_notification_description = f'{self.request.user} declined your request to Resume the Moogt, "{moogt}" Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'

                elif moogt_activity.status == ActivityStatus.WAITING.value:
                    moogt_activity.status = activity_status
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    moogt_activity.save()

                    self.create_or_update_bundle(moogt, moogt_activity)

                    self.push_notification_title = f'{self.request.user} Declined request to Resume Moogt'
                    self.push_notification_description = f'{self.request.user} declined your request to Resume the Moogt, "{moogt}"'

            else:
                self.create_or_update_bundle(
                    moogt_activity.moogt, moogt_activity)
                verb = "declined"

                moogt_activity.status = activity_status
                moogt_activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                moogt_activity.save()

                self.push_notification_title = f'{self.request.user} Declined request to Resume Moogt'
                self.push_notification_description = f'{self.request.user} declined your request to Resume the Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.CANCELLED.value:
            send_notification = False
            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            moogt_activity.save()

        if send_notification:
            self.send_notification(moogt_activity.user,
                                   moogt_activity.moogt,
                                   verb,
                                   NOTIFICATION_TYPES.moogt_request_resolved,
                                   data={'moogt': MoogtNotificationSerializer(moogt_activity.moogt).data,
                                         'activity': MoogtActivitySerializer(moogt_activity).data},
                                   push_notification_title=self.push_notification_title,
                                   push_notification_description=self.push_notification_description
                                   )

        return Response(self.get_serializer(moogt_activity).data)


class MakeDeleteMoogtRequestApiView(ActivityCreationValidationMixin,
                                    generics.GenericAPIView,
                                    mixins.CreateModelMixin):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        self.moogt: Moogt = get_object_or_404(Moogt, pk=moogt_id)
        self.verb = "requested to delete"

        if self.request.user == self.moogt.get_moderator():
            self.push_notification_title = f'{self.request.user} requested to Delete Moogt as Moderator'
            self.push_notification_description = f'{self.request.user} requested to delete the Moogt as a Moderator, "{self.moogt}"'
        else:
            self.push_notification_title = f'{self.request.user} requested to Delete Moogt'
            self.push_notification_description = f'{self.request.user} requested to Delete the Moogt, "{self.moogt}"'

        self.validate_delete_request(self.moogt)
        self.validate(self.moogt, MoogtActivityType.DELETE_REQUEST.value)

        request.data['moogt'] = self.moogt
        request.data['type'] = MoogtActivityType.DELETE_REQUEST.value
        request.data['actor'] = self.moogt.get_opponent(request.user)
        return self.create(request, *args, **kwargs)

    def validate_delete_request(self, moogt: Moogt):
        pending_delete_request = moogt.activities.filter(type=MoogtActivityType.DELETE_REQUEST.value,
                                                         status=ActivityStatus.PENDING.value).exists()
        if pending_delete_request:
            raise ValidationError('There is already a pending request')

    def perform_create(self, serializer):
        self.perform_create_with_notifications_moogt(serializer)


class DeleteMoogtRequestActionApiView(ActivityActionValidationMixin,
                                      generics.GenericAPIView):
    serializer_class = MoogtActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = kwargs.get('pk')
        moogt_activity = get_object_or_404(MoogtActivity, pk=activity_id)
        moogt: Moogt = moogt_activity.moogt

        if moogt_activity.type != MoogtActivityType.DELETE_REQUEST.name:
            raise ValidationError(
                "This endpoint is to take action only on Card requests")

        activity_status = self.validate(moogt_activity)
        verb = "deleted"
        send_notification = True

        if activity_status == ActivityStatus.ACCEPTED.value:
            argument_ids = moogt.arguments.values_list('id', flat=True)

            views = View.objects.filter(content__isnull=True,
                                        parent_argument__in=argument_ids)
            views.delete()

            moogt.delete()
            moogt.arguments.update(is_removed=True)

            moogt_activity.status = activity_status

            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
            moogt_activity.save()

            self.push_notification_title = f'{self.request.user} Approved request to Delete Moogt'
            self.push_notification_description = f'{self.request.user} approved your request to Delete the Moogt, "{moogt}"'

        elif activity_status == ActivityStatus.DECLINED.value:
            if moogt.get_moderator():
                if moogt_activity.status == ActivityStatus.PENDING.value:
                    moogt_activity.status = ActivityStatus.WAITING.value
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    moogt_activity.save()

                    self.push_notification_title = f'{self.request.user} declined request to Delete Moogt - Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)}'
                    self.push_notification_description = f'{self.request.user} declined request to delete the Moogt, "{moogt}" Waiting on {get_awaited_user(request.user, moogt_activity.user, moogt)} to also vote.'

                elif moogt_activity.status == ActivityStatus.WAITING.value:
                    moogt_activity.status = activity_status
                    moogt_activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    moogt_activity.save()

                    self.push_notification_title = f'{self.request.user} Declined request to Delete Moogt'
                    self.push_notification_description = f'{self.request.user} declined your request to delete the Moogt, "{moogt}"'
            else:
                moogt_activity.status = activity_status
                moogt_activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                moogt_activity.save()

                self.push_notification_title = f'{self.request.user} Declined request to Delete Moogt'
                self.push_notification_description = f'{self.request.user} declined your request to delete the Moogt, "{moogt}"'

                verb = "declined"

        elif activity_status == ActivityStatus.CANCELLED.value:
            send_notification = False
            moogt_activity.status = activity_status
            moogt_activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            moogt_activity.save()

        if send_notification:
            self.create_or_update_bundle(moogt_activity.moogt, moogt_activity)
            self.send_notification(moogt_activity.user,
                                   moogt_activity.moogt,
                                   verb,
                                   NOTIFICATION_TYPES.moogt_request_resolved,
                                   data={'activity': MoogtActivitySerializer(
                                       moogt_activity).data},
                                   push_notification_title=self.push_notification_title,
                                   push_notification_description=self.push_notification_description
                                   )

        return Response(self.get_serializer(moogt_activity).data)


class GetMoogtHighlightsApiView(SerializerExtensionsAPIViewMixin,
                                generics.GenericAPIView):
    serializer_class = ArgumentSerializer
    extensions_expand = ['react_to', 'reply_to',
                         'activities', 'modified_child', 'images', 'user', 'user__profile']

    def get(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        all_arguments = moogt.arguments.prefetch_related_objects()

        all_arguments = all_arguments.annotate(
            applauds_count=Count('stats__applauds'),
            endorsements_count=Count('argument_reactions',
                                     filter=Q(
                                         argument_reactions__reaction_type=ReactionType.ENDORSE.name,
                                         argument_reactions__is_removed=False)
                                     ),
            disagreements_count=Count('argument_reactions',
                                      filter=Q(
                                          argument_reactions__reaction_type=ReactionType.DISAGREE.name,
                                          argument_reactions__is_removed=False)
                                      ),
        )

        most_applauded = all_arguments.filter(
            applauds_count__gt=0).order_by('-applauds_count')
        if most_applauded.count() > 0:
            most_applauded = most_applauded.prefetch_related_objects().first()
        else:
            most_applauded = None

        most_agreed = all_arguments.filter(
            endorsements_count__gt=0).order_by('-endorsements_count')
        if most_agreed.count() > 0:
            most_agreed = most_agreed.prefetch_related_objects().first()
        else:
            most_agreed = None

        most_disagreed = all_arguments.filter(
            disagreements_count__gt=0).order_by('-disagreements_count')
        if most_disagreed.count() > 0:
            most_disagreed = most_disagreed.prefetch_related_objects().first()
        else:
            most_disagreed = None

        most_commented = all_arguments.filter(
            comment_count__gt=0).order_by('-comment_count')
        if most_commented.count() > 0:
            most_commented = most_commented.prefetch_related_objects().first()
        else:
            most_commented = None

        return Response({'most_applauded': self.get_serializer(most_applauded).data,
                         'most_agreed': self.get_serializer(most_agreed).data,
                         'most_disagreed': self.get_serializer(most_disagreed).data,
                         'most_commented': self.get_serializer(most_commented).data})


class MakeMoogtDonationApiView(SerializerExtensionsAPIViewMixin,
                               generics.CreateAPIView):
    serializer_class = DonationSerializer

    @ transaction.atomic()
    def post(self, request, *args, **kwargs):
        self.moogt = get_object_or_404(Moogt, pk=kwargs.get('pk'))

        if request.user == self.moogt.get_opposition() or request.user == self.moogt.get_proposition():
            raise rest_framework.exceptions.PermissionDenied(
                'You cannot donate to your own moogt.')

        if request.user == self.moogt.get_moderator():
            raise rest_framework.exceptions.PermissionDenied(
                'Moderators cannot donate to to its moogt.')

        self.validate_account()
        self.validate_char_limit()
        self.make_donation()

        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(moogt=self.moogt)

    def validate_account(self):
        user: MoogtMedaUser = self.request.user
        amount = self.request.data.get('amount')
        if amount > user.wallet.credit:
            raise ValidationError(
                'You do not have enough credit to donate for the moogt.')

    def validate_char_limit(self):
        amount = self.request.data.get('amount')
        message = self.request.data.get('message', '')
        if message:
            char_count = len(message)
            level = Donation.get_equivalence_level(amount)

            limit_dict = {
                DonationLevel.LEVEL_1.name: 50,
                DonationLevel.LEVEL_2.name: 75,
                DonationLevel.LEVEL_3.name: 100,
                DonationLevel.LEVEL_4.name: 150,
                DonationLevel.LEVEL_5.name: 200,
            }

            if char_count > limit_dict[level]:
                raise ValidationError(
                    "Char limit passed for this level of donation")

    def make_donation(self):
        user: MoogtMedaUser = self.request.user
        amount = self.request.data.get('amount')
        self.request.data['level'] = Donation.get_equivalence_level(
            self.request.data.get('amount'))
        user.wallet.credit = user.wallet.credit - amount
        user.wallet.save()


class ListDonationsApiView(SerializerExtensionsAPIViewMixin,
                           generics.ListAPIView):
    serializer_class = DonationSerializer

    def get_queryset(self):
        moogt_id = self.kwargs.get('pk')
        self.moogt = get_object_or_404(Moogt, pk=moogt_id)
        self.donation_for_proposition = self.request.query_params.get(
            'donation_for_proposition', 'true')
        return self.moogt.donations.filter(donation_for_proposition=json.loads(self.donation_for_proposition)) \
            .order_by('-created_at')

    def get_highest_donation(self):
        return self.get_serializer(self.get_queryset().order_by('-amount', '-created_at').first()).data

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)

        return Response({
            **response.data,
            'highest': self.get_highest_donation()
        })


class QuitMoogtApiView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView, BasicMoogtExtensions):
    serializer_class = MoogtSerializer

    def get(self, request, *args, **kwargs):
        moogt_id = self.kwargs.get('pk')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        # Validate it's a moogt participant that is trying to end this moogt.
        if request.user not in [moogt.get_proposition(), moogt.get_opposition(), moogt.get_moderator()]:
            raise ValidationError('Non-participant cannot quit this moogt')

        if not moogt.func_is_current_turn(request.user):
            raise ValidationError(
                "User can't quit moogt if it's not their turn")

        moogt_queryset = Moogt.objects.filter(id=moogt.id)
        if request.user == moogt.get_moderator():
            moogt_queryset.update(moderator=None)
            data = {'moogt': MoogtNotificationSerializer(moogt).data}
        else:
            quit_moogts(moogt_queryset, request.user)
            moogt_broke_off = MoogtStatus.objects.get(
                moogt=moogt, status=MoogtStatus.STATUS.broke_off)
            data = {'status': MoogtStatusSerializer(moogt_broke_off).data,
                    'moogt': MoogtNotificationSerializer(moogt).data}

        # TODO Move the moogt_activities and create_bundle to the quit_moogts function

        moogt_activity = MoogtActivity.objects.create(
            moogt=moogt,
            user=request.user,
            type=MoogtActivityType.QUIT.value,
            status=ActivityStatus.ACCEPTED.value,
        )
        ActivityActionValidationMixin().create_or_update_bundle(moogt, moogt_activity)

        recipient = []

        if self.request.user == moogt.get_proposition():
            recipient = [moogt.get_opposition(), moogt.get_moderator(),
                         *moogt.followers.all()]

        elif self.request.user == moogt.get_opposition():
            recipient = [moogt.get_proposition(), moogt.get_moderator(),
                         *moogt.followers.all()]

        elif self.request.user == moogt.get_moderator():
            recipient = [moogt.get_proposition(), moogt.get_opposition(),
                         *moogt.followers.all()]

        filtered_recipient = list(filter(lambda rec: (rec != None), recipient))

        notify.send(
            recipient=filtered_recipient,
            sender=self.request.user,
            verb='quit',
            send_email=False,
            type=NOTIFICATION_TYPES.moogt_status,
            send_telegram=True,
            target=moogt,
            data=data,
            push_notification_title=f'{self.request.user} Quit!',
            push_notification_description=f'{self.request.user} has quit the Moogt, "{moogt}"'
        )

        return Response(data=self.get_serializer(moogt).data, status=status.HTTP_200_OK)


class GetUsersFollowingMoogtApiView(generics.ListAPIView, ViewArgumentReactionMixin):
    serializer_class = MoogtMedaUserSerializer

    def get(self, request, *args, **kwargs):
        moogt = get_object_or_404(Moogt, pk=kwargs.get('pk'))

        self.queryset = self.sort_by_follower_count_and_following_status(
            request, moogt.followers)

        return self.list(request, *args, **kwargs)


class MoogtReportApiView(ReportMixin, generics.CreateAPIView):
    serializer_class = MoogtReportSerializer

    def post(self, request, *args, **kwargs):
        moogt_id = kwargs.get('pk')
        self.moogt = get_object_or_404(Moogt, pk=moogt_id)

        self.validate(created_by=self.moogt.get_proposition(
        ), reported_by=request.user, queryset=self.moogt.reports.all())
        self.validate(created_by=self.moogt.get_opposition(
        ), reported_by=request.user, queryset=self.moogt.reports.all())
        self.validate(created_by=self.moogt.get_moderator(
        ), reported_by=request.user, queryset=self.moogt.reports.all())

        return super().post(request, args, kwargs)

    def perform_create(self, serializer):
        report = serializer.save(
            moogt=self.moogt, reported_by=self.request.user)
        self.notify_admins(report)
