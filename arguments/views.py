import copy
import json


from django.db.models import Q
import django.core
import rest_framework.exceptions
from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models import F, Case, When, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_comments_xtd.api.serializers import WriteCommentSerializer
from queryset_sequence import QuerySetSequence
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin

from api.enums import ViewType, ReactionType
from api.mixins import ReportMixin, ViewArgumentReactionMixin, ApplaudMixin, BrowseReactionsMixin, CommentMixin, \
    ActivityActionValidationMixin, ActivityCreationValidationMixin, CreateImageMixin
from api.pagination import SmallResultsSetPagination
from api.serializers import CommentSerializer
from api.utils import get_union_queryset, inflate_referenced_objects
from arguments.models import Argument, ArgumentActivity, ArgumentActivityType
from arguments.serializers import ArgumentReportSerializer, ArgumentSerializer, ArgumentImageSerializer, \
    ArgumentActivitySerializer, ArgumentReactionSerializer, ListArgumentSerialier, \
    ArgumentNotificationSerializer
from arguments.utils import notify_ws_clients_for_argument
from meda.enums import ActivityStatus
from meda.enums import ArgumentType, MoogtEndStatus
from meda.models import AbstractActivityAction
from moogts.enums import MoogtWebsocketMessageType, MoogtActivityType
from moogts.models import Moogt, MoogtActivityBundle
from moogts.serializers import MoogtNotificationSerializer
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from users.models import Activity, ActivityType, CreditPoint
from users.serializers import MoogtMedaUserSerializer
from views.models import View
from views.serializers import ViewSerializer
from .enums import ArgumentReactionType
from .extensions import BasicArgumentSerializerExtensions
from .pagination import ArgumentListPagination, CustomCursorPagination


def get_awaited_user(requesting_user, acting_user, moogt):
    users = [moogt.get_opposition(), moogt.get_moderator(),
             moogt.get_proposition()]
    filtered_user = filter(lambda user: user !=
                           requesting_user and user != acting_user, users)
    return list(filtered_user)[0]


class CreateArgumentView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView, CreateImageMixin,
                         BasicArgumentSerializerExtensions):
    serializer_class = ArgumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['post']

    extensions_auto_optimize = True

    def post(self, request, *args, **kwargs):
        moogt_id = request.data.get('moogt_id')
        moogt = get_object_or_404(Moogt, pk=moogt_id)

        if request.user != moogt.get_proposition() and request.user != moogt.get_opposition() and request.user != moogt.get_moderator():
            return Response('Non-proposition or opposition user attempting to add an argument.',
                            status=status.HTTP_403_FORBIDDEN)

        reply_to = None
        if request.data.get('reply_to'):
            reply_to = get_object_or_404(
                Argument, id=request.data.get('reply_to'))

        react_to = None
        if request.data.get('react_to'):
            react_to = get_object_or_404(
                Argument, id=request.data.get('react_to'))

        if react_to and not request.data.get('reaction_type'):
            raise rest_framework.exceptions.ValidationError(
                "You cannot create a reaction argument without reaction_type.")

        with transaction.atomic():
            argument = self.create_argument(moogt, react_to, reply_to, request)
            argument.moogt.func_end_moogt()

        self.send_notification(argument, moogt, request)

        async_to_sync(notify_ws_clients_for_argument)(argument)

        return Response(self.get_serializer(argument).data, status=status.HTTP_201_CREATED)

    def create_argument(self, moogt, react_to, reply_to, request):
        argument_serializer = ArgumentSerializer(
            data=request.data, context={'request': request})
        if not argument_serializer.is_valid():
            raise rest_framework.exceptions.ValidationError(
                argument_serializer.errors)

        moogt.func_skip_expired_turns()

        if request.data.get('type') == ArgumentType.CONCLUDING.name:
            if not moogt.get_has_ended() or moogt.quit_by == request.user:
                raise rest_framework.exceptions.ValidationError(
                    "You cannot create this type of argument.")

            if moogt.arguments.filter(type=ArgumentType.CONCLUDING.name, user=request.user).count() == 1:
                raise rest_framework.exceptions.ValidationError(
                    "You cannot create two concluding arguments")

            argument = argument_serializer.save(
                user=request.user, moogt=moogt, type=request.data.get('type'))
        else:
            if not moogt.func_is_current_turn(request.user):
                raise rest_framework.exceptions.ValidationError(
                    "It is not this user's turn for creating an argument.")

            if moogt.get_is_paused():
                raise rest_framework.exceptions.ValidationError(
                    'You cannot create an argument while a moogt is paused.')

            if moogt.quit_by == request.user:
                raise rest_framework.exceptions.ValidationError(
                    "You cannot create an argument on a moogt you quit")

            argument = argument_serializer.save(
                user=request.user, moogt=moogt, reply_to=reply_to, react_to=react_to)

            if request.user == moogt.get_moderator():
                argument.set_type(ArgumentType.MODERATOR_ARGUMENT.name)
                argument.save()
                
            if request.user != moogt.get_moderator():
                self.update_moogt(request.user, moogt,
                                  request.data.get('status'))

        self.record_activity(request.user, argument)
        self.create_image(argument)
        return argument

    def send_notification(self, argument, moogt, request):
        recipient = []

        if request.user == moogt.get_proposition():
            recipient = [moogt.get_opposition(), moogt.get_moderator()]

        elif request.user == moogt.get_opposition():
            recipient = [moogt.get_proposition(), moogt.get_moderator()]

        elif request.user == moogt.get_moderator():
            recipient = [moogt.get_proposition(), moogt.get_opposition()]

        type = NOTIFICATION_TYPES.moogt_card
        if self.request.data.get('type') == ArgumentType.CONCLUDING.name:
            type = NOTIFICATION_TYPES.moogt_conclude

        filtered_recipient = list(filter(lambda rec: (rec != None), recipient))

        if request.user == moogt.get_moderator():
            notify.send(
                recipient=filtered_recipient,
                sender=request.user,
                verb="replied",
                action_object=argument,
                target=argument.moogt,
                send_email=False,
                type=type,
                data={'moogt': MoogtNotificationSerializer(
                    argument.moogt).data},
                send_telegram=True,
                push_notification_title=f'{request.user} Submitted a card as Moderator!',
                push_notification_description=f'{request.user} submitted a card as Moderator in the Moogt, "{argument.moogt}"'
            )

        else:
            notify.send(
                recipient=filtered_recipient,
                sender=request.user,
                verb="replied",
                action_object=argument,
                target=argument.moogt,
                send_email=False,
                type=type,
                data={'moogt': MoogtNotificationSerializer(
                    argument.moogt).data},
                send_telegram=True,
                push_notification_title=f'{request.user} Submitted a new Card!',
                push_notification_description=f'{request.user} submitted a new card in the Moogt, "{argument.moogt}"'
            )


    @staticmethod
    def has_user_requested_to_end_moogt(user, moogt):
        if user == moogt.get_proposition():
            return moogt.get_end_requested_by_proposition()
        elif user == moogt.get_opposition():
            return not moogt.get_end_requested_by_proposition()

    @staticmethod
    def update_moogt(user, moogt: Moogt, debate_status):
        if moogt.get_started_at() is None:
            moogt.set_started_at(timezone.now())
            
        if user == moogt.get_proposition():
            moogt.set_next_turn_proposition(False)
        elif user == moogt.get_opposition():
            moogt.set_next_turn_proposition(True)

        moogt.set_last_posted_by_proposition(
            not moogt.get_next_turn_proposition())

        moogt.set_latest_argument_added_at(timezone.now())
        moogt.activities.filter(type=MoogtActivityType.CARD_REQUEST.name,
                                status=ActivityStatus.PENDING.value).delete()

        if moogt.get_end_requested() or moogt.quit_by:
            moogt.set_has_ended(True)

        if not moogt.get_has_ended():
            if debate_status != "continue":
                moogt.set_end_requested(True)
                moogt.set_end_requested_by_proposition(
                    user == moogt.proposition)
                if debate_status == 'concede':
                    moogt.set_end_request_status(MoogtEndStatus.concede())
                    moogt.set_has_ended(True)
                elif debate_status == 'disagree':
                    moogt.set_end_request_status(MoogtEndStatus.disagree())
                else:
                    raise django.core.exceptions.SuspiciousOperation(
                        "Invalid End Request Status.")

        moogt.save()

    @staticmethod
    def record_activity(user, argument):
        activity = Activity()
        activity.profile = user.profile
        activity.type = ActivityType.create_argument.name
        activity.object_id = argument.id
        activity.save()


class UpvoteDownvoteArgumentView(generics.GenericAPIView):
    http_method_names = ['post']
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        argument_id = kwargs.get('pk')
        argument = get_object_or_404(Argument, pk=argument_id)

        moogt = argument.get_moogt()
        if request.user == moogt.get_proposition() or request.user == moogt.get_opposition():
            raise rest_framework.exceptions.ValidationError(
                "This user can't perform this action.")

        action = request.data.get('action')
        argument_stats = argument.stats
        if action == "upvote":
            self.maybe_upvote(argument, request.user)
        elif action == "downvote":
            self.maybe_downvote(argument, request.user)
        else:
            raise rest_framework.exceptions.ValidationError('Invalid action.')

        return Response({'success': True,
                         'num_upvotes': argument_stats.upvotes.count(),
                         'num_downvotes': argument_stats.downvotes.count()},
                        status=status.HTTP_200_OK)

    @staticmethod
    def maybe_upvote(argument, user):
        argument_stats = argument.stats
        if argument_stats.upvotes.filter(id=user.id).exists():
            argument_stats.upvotes.remove(user)
        else:
            argument_stats.upvotes.add(user)
            activity = Activity.record_activity(
                user.profile, ActivityType.upvote_argument.name, argument.id)

            CreditPoint.create_upvote_downvote_credit_point(
                ActivityType.upvote_argument, activity, argument)

            if argument_stats.downvotes.filter(id=user.id).exists():
                argument_stats.downvotes.remove(user)

    @staticmethod
    def maybe_downvote(argument, user):
        argument_stats = argument.stats
        if argument_stats.downvotes.filter(id=user.id).exists():
            argument_stats.downvotes.remove(user)
        else:
            argument_stats.downvotes.add(user)
            activity = Activity.record_activity(
                user.profile, ActivityType.downvote_argument.name, argument.id)

            CreditPoint.create_upvote_downvote_credit_point(
                ActivityType.downvote_argument, activity, argument)

            if argument_stats.upvotes.filter(id=user.id).exists():
                argument_stats.upvotes.remove(user)


class ArgumentReactionApiView(SerializerExtensionsAPIViewMixin,
                              ViewArgumentReactionMixin,
                              generics.GenericAPIView,
                              BasicArgumentSerializerExtensions):
    serializer_class = ArgumentSerializer
    extensions_auto_optimize = True

    def post(self, request, *args, **kwargs):
        if 'type' not in request.data:
            raise rest_framework.exceptions.ValidationError(
                "Request needs type of reaction")
        if 'argument_id' not in request.data:
            raise rest_framework.exceptions.ValidationError(
                "Request needs argument id")

        argument = get_object_or_404(Argument, pk=request.data['argument_id'])

        if (argument.moogt.proposition == request.user or argument.moogt.opposition == request.user) \
                and not argument.moogt.has_ended \
                and request.data.get('content'):
            raise rest_framework.exceptions.ValidationError(
                "Moogt participants can not react with statement on live Moogt")

        reaction_view = self.react(
            request, argument, ViewType.ARGUMENT_REACTION.name)
        if request.version == 'v1':
            argument = Argument.objects.prefetch_related_objects().get(pk=argument.id)
            serialized_data = self.get_serializer(argument).data
        elif request.version == 'v2':
            if reaction_view:
                self.serializer_class = ViewSerializer
                self.extensions_expand = {'parent', 'images'}
                reaction_view = View.objects.get(pk=reaction_view.id)
                serialized_data = self.get_serializer(reaction_view).data
            else:
                argument = Argument.objects.prefetch_related_objects().get(pk=argument.id)
                serialized_data = self.get_serializer(argument).data
        else:
            serialized_data = None

        return Response(serialized_data, status.HTTP_200_OK)


class ApplaudArgumentApiView(SerializerExtensionsAPIViewMixin,
                             ApplaudMixin,
                             generics.GenericAPIView,
                             BasicArgumentSerializerExtensions):
    serializer_class = ArgumentSerializer

    extensions_auto_optimize = True

    def post(self, request, *args, **kwargs):
        argument = get_object_or_404(Argument, pk=kwargs.get('pk'))
        has_applauded = self.maybe_applaud(argument, self.request.user)
        argument = Argument.objects.prefetch_related_objects().get(pk=argument.id)

        if has_applauded and self.request.user != argument.user:
            notify.send(recipient=argument.user,
                        sender=self.request.user,
                        verb="applauded",
                        send_email=False,
                        send_telegram=True,
                        type=NOTIFICATION_TYPES.argument_applaud,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=argument,
                        data={'argument': ArgumentNotificationSerializer(
                            argument).data},
                        push_notification_title=f'{self.request.user} applauded your Moogt Card!',
                        push_notification_description=f'{request.user} applauded your Moogt Card, "{argument}" in the Moogt, "{argument.moogt}"'
                        )
        elif not has_applauded and self.request.user != argument.user:
            Notification.objects.remove_notification(
                argument, self.request.user, NOTIFICATION_TYPES.argument_applaud)

        return Response(self.get_serializer(argument).data, status=status.HTTP_200_OK)


class BrowseArgumentReactionsApiView(SerializerExtensionsAPIViewMixin,
                                     BrowseReactionsMixin,
                                     generics.ListAPIView):
    serializer_class = ArgumentReactionSerializer
    all_reaction_qs = {}

    def get_queryset(self):
        return self.get_all_reactions_queryset()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            page = inflate_referenced_objects(
                union_qs=page, **self.all_reaction_qs, object_type_field='object_type')
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        queryset = inflate_referenced_objects(union_qs=queryset,
                                              **self.all_reaction_qs,
                                              object_type_field='object_type')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_moogter_reactions(self, argument):
        reaction_type = self.request.query_params.get('type', None)
        if reaction_type == ReactionType.ENDORSE.name:
            reaction_type = ArgumentReactionType.ENDORSEMENT.name
        elif reaction_type == ReactionType.DISAGREE.name:
            reaction_type = ArgumentReactionType.DISAGREEMENT.name

        if reaction_type is not None:
            moogter_reactions = argument.moogter_reactions.filter(
                reaction_type=reaction_type)
        else:
            moogter_reactions = argument.moogter_reactions

        own_only = json.loads(self.request.query_params.get('own', 'false'))
        if self.request.user.is_authenticated and own_only:
            return moogter_reactions.filter(user=self.request.user)

        # If user is authenticated, exclude his/her own reactions.
        if self.request.user.is_authenticated:
            return moogter_reactions.exclude(user=self.request.user)

    def get_all_reactions_queryset(self):
        argument_id = self.kwargs.get('pk')
        argument: Argument = get_object_or_404(
            Argument.objects.prefetch_related_objects(), pk=argument_id)
        # These are the reactions by non-moogters.
        query_set = self.get_reactions_queryset(
            argument.argument_reactions.filter(content__isnull=False))
        # These are the reactions by moogters.
        moogters_reaction_qs = self.get_moogter_reactions(argument)

        self.all_reaction_qs = {'non_moogter_reaction': query_set,
                                'moogter_reaction': moogters_reaction_qs}

        return get_union_queryset(**self.all_reaction_qs,
                                  datetime_field='created_at',
                                  object_type_field='object_type')


class GetArgumentReactingUsersApiView(SerializerExtensionsAPIViewMixin, generics.ListAPIView,
                                      ViewArgumentReactionMixin):
    serializer_class = MoogtMedaUserSerializer
    pagination_class = SmallResultsSetPagination

    def get(self, request, *args, **kwargs):
        argument = get_object_or_404(Argument, pk=kwargs.get('pk'))

        self.queryset = self.get_reacting_users(request, argument)

        return self.list(request, *args, **kwargs)


class ArgumentCommentCreateApiView(CommentMixin, generics.GenericAPIView, BasicArgumentSerializerExtensions):
    serializer_class = WriteCommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        argument_id = request.data['argument_id']

        argument = get_object_or_404(Argument, pk=argument_id)

        if (request.user == argument.moogt.proposition or request.user == argument.moogt.opposition) \
                and not argument.moogt.has_ended:
            return Response("Sorry You can't comment on your ongoing moogt", status.HTTP_400_BAD_REQUEST)

        comment = self.comment(request, argument)
        serializer = CommentSerializer(
            comment, context=self.get_serializer_context())

        if self.request.user != argument.user:
            notify.send(recipient=argument.user,
                        sender=self.request.user,
                        verb="commented",
                        send_email=False,
                        send_telegram=True,
                        type=NOTIFICATION_TYPES.argument_comment,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=argument,
                        data={'argument': ArgumentNotificationSerializer(argument).data,
                              'comment': serializer.data},
                        push_notification_title=f'{self.request.user} commented on your Moogt Card!',
                        push_notification_description=f'{self.request.user} commented on your Moogt Card, "{argument}" with, "{comment.comment}"'
                        )

        return Response(serializer.data, status.HTTP_201_CREATED)


class ListArgumentCommentsApiView(SerializerExtensionsAPIViewMixin, CommentMixin, generics.ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = SmallResultsSetPagination
    extensions_expand = ['user__profile']

    def get_queryset(self):
        argument_id = self.kwargs.get('pk')
        argument = get_object_or_404(Argument, pk=argument_id)

        return self.get_comments(self.request, argument)


class ListArgumentsApiView(SerializerExtensionsAPIViewMixin, BasicArgumentSerializerExtensions, generics.ListAPIView):
    serializer_class = ListArgumentSerialier
    pagination_class = ArgumentListPagination

    def get_queryset(self):
        moogt_id = self.kwargs.get('pk')
        self.moogt = get_object_or_404(Moogt, pk=moogt_id)

        if self.moogt.opposition != self.request.user and self.moogt.proposition != self.request.user:
            self.extensions_exclude = ['activities']

        arguments = self.moogt.arguments \
            .exclude(type=ArgumentType.CONCLUDING.name) \
            .order_by('-created_at') \
            .filter(modified_parent=None) \
            .prefetch_related_objects() \
            .annotate(created=F('created_at'))

        bundles = MoogtActivityBundle.objects \
            .annotate(activities_count=Count('activities')) \
            .filter(moogt=self.moogt, activities_count__gt=0) \
            .annotate(created=Case(
                When(updated_at__isnull=True, then=(F('created_at'))),
                default=F('updated_at')))

        statuses = self.moogt.statuses.annotate(created=F('created_at'))

        queryset = QuerySetSequence(arguments, bundles, statuses)

        return queryset

    def paginate_queryset(self, queryset):
        """
        Return a single page of results, or `None` if pagination is disabled.
        """
        if self.paginator is None:
            return None

        offset = (self.get_unread_count(queryset) -
                  self.paginator.get_page_size(self.request)) + 1
        offset = offset if offset > 0 else 0
        return self.paginator.paginate_queryset(queryset, self.request, view=self, offset=offset)

    def get_unread_count(self, queryset):
        latest_read_by = self.request.user.read_moogts.filter(
            moogt=self.moogt).first()

        if self.request.user in self.moogt.followers.all() and latest_read_by:
            latest_read_at = latest_read_by.latest_read_at
            return queryset.filter(created_at__gt=latest_read_at).count()

        return 0


class ListConcludingArgumentsApiView(SerializerExtensionsAPIViewMixin, generics.ListAPIView,
                                     BasicArgumentSerializerExtensions):
    serializer_class = ArgumentSerializer
    pagination_class = SmallResultsSetPagination

    def get_queryset(self):
        moogt = get_object_or_404(Moogt, pk=self.kwargs.get('pk'))

        if moogt.opposition != self.request.user and moogt.proposition != self.request.user:
            self.extensions_exclude = ['activities']

        queryset = moogt.arguments \
            .filter(type=ArgumentType.CONCLUDING.name) \
            .filter(modified_parent=None) \
            .order_by('-created_at')

        return queryset


class CreateEditRequestApiView(ActivityCreationValidationMixin,
                               SerializerExtensionsAPIViewMixin,
                               CreateImageMixin,
                               generics.GenericAPIView, ):
    serializer_class = ArgumentSerializer

    extensions_expand = ['modified_child']

    def post(self, request, *args, **kwargs):
        argument_id = request.data.pop("argument_id", None)

        if request.data.get('argument') is None:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not create this request with no argument.")
        if argument_id is None:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not create this argument with no argument id")

        argument = get_object_or_404(Argument, pk=argument_id)
        verb = "requested to edit"

        if self.request.user == argument.moogt.get_moderator():
            self.push_notification_title = f'{self.request.user} requested to Edit Card as Moderator'
            self.push_notification_description = f'{self.request.user} requested to edit a Moogt Card, "{argument}"  as Moderator in the Moogt, "{argument.moogt}"'
        else:
            self.push_notification_title = f'{self.request.user} requested to Edit a Moogt Card'
            self.push_notification_description = f'{self.request.user} requested to edit a Moogt Card, "{argument}" in the Moogt, "{argument.moogt}"'

        self.validate(argument, ArgumentActivityType.EDIT.value)

        if argument.user != self.request.user and self.request.user == argument.moogt.get_moderator():
            raise rest_framework.exceptions.PermissionDenied(
                "Moderators can not make edit request on an argument they haven't created.")

        child_argument = copy.deepcopy(argument)

        child_argument.pk = None
        child_argument.save()
        child_argument.is_edited = True

        serializer = self.get_serializer(
            child_argument, data=request.data, partial=True)
        if not serializer.is_valid():
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not create this argument with invalid parameters")

        child_argument = serializer.save()
        argument.modified_child = child_argument
        argument.save()

        self.create_image(child_argument)

        activity = ArgumentActivity(argument=argument,
                                    type=ArgumentActivityType.EDIT.value,
                                    status=ActivityStatus.PENDING.value,
                                    user=request.user,
                                    actor=argument.moogt.get_opponent(request.user))
        activity.save()

        self.send_argument_request_notifications(argument, activity, verb)

        return Response(self.get_serializer(argument).data, status=status.HTTP_201_CREATED)


class CreateDeleteRequestApiView(ActivityCreationValidationMixin,
                                 SerializerExtensionsAPIViewMixin,
                                 generics.GenericAPIView):
    serializer_class = ArgumentActivitySerializer

    def post(self, request, *args, **kwargs):
        argument_id = request.data.pop("argument_id", None)

        if argument_id == None:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not delete an argument without id.")

        argument = get_object_or_404(Argument, pk=argument_id)
        verb = "requested to delete"

        self.push_notification_title = f'{self.request.user} requested to Delete a Moogt Card'
        self.push_notification_description = f'{self.request.user} requested to delete a Moogt Card, "{argument}" in the Moogt, "{argument.moogt}"'

        self.validate(argument, ArgumentActivityType.DELETE.value)

        activity = ArgumentActivity(argument_id=argument_id,
                                    type=ArgumentActivityType.DELETE.value,
                                    status=ActivityStatus.PENDING.value,
                                    user=request.user,
                                    actor=argument.moogt.get_opponent(request.user))
        activity.save()

        self.send_argument_request_notifications(argument, activity, verb)

        return Response(self.get_serializer(activity).data, status=status.HTTP_200_OK)


class ListArgumentActivityApiView(SerializerExtensionsAPIViewMixin, generics.ListAPIView):
    serializer_class = ArgumentActivitySerializer
    pagination_class = SmallResultsSetPagination

    def get_queryset(self):
        argument_id = self.kwargs.get('pk')
        argument = get_object_or_404(Argument, pk=argument_id)

        return argument.activities.order_by('-created_at')


class DeleteRequestActionApiView(ActivityActionValidationMixin,
                                 SerializerExtensionsAPIViewMixin,
                                 generics.GenericAPIView):
    serializer_class = ArgumentActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = request.data.pop("activity_id", None)

        if activity_id is None:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not make a delete action request with no activity id.")

        activity = get_object_or_404(ArgumentActivity, pk=activity_id)
        verb = None
        argument = activity.argument
        notification_include_argument = True
        push_notification_title = 'You have a new Notification'
        push_notification_description = 'You have a new Notification'

        if activity.type != ArgumentActivityType.DELETE.value:
            raise rest_framework.exceptions.ValidationError(
                "This endpoint is to take action only on deleting a card")

        action_type = self.validate(activity)

        if action_type == ActivityStatus.ACCEPTED.value:
            # Delete The argument
            verb = "approved"
            notification_include_argument = False
            argument_clone = copy.deepcopy(argument)
            argument_clone.pk = None
            argument_clone.type = ArgumentType.DELETED.name
            argument_clone.argument = ""
            argument_clone.save()

            argument.delete()
            # The reaction without statements should be deleted as well.
            argument.argument_reactions.filter(content__isnull=True).delete()
            activity.status = ActivityStatus.ACCEPTED.value
            activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
            activity.save()

            argument_clone.activities.set(argument.activities.all())
            async_to_sync(notify_ws_clients_for_argument)(argument,
                                                          MoogtWebsocketMessageType.ARGUMENT_DELETE_APPROVED.value)

            push_notification_title = f'{self.request.user} Approved request to Delete Moogt Card'
            push_notification_description = f'{self.request.user} approved your request to Delete Moogt Card, "{argument.moogt}"'

        elif action_type == ActivityStatus.DECLINED.value:
            if argument.moogt.get_moderator():
                if activity.status == ActivityStatus.PENDING.value:
                    activity.status = ActivityStatus.WAITING.value

                    activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    activity.save()

                    verb = "waiting"

                    self.push_notification_title = f'{self.request.user} declined request to Delete Moogt Card - Waiting on {get_awaited_user(request.user, activity.user,argument.moogt )}'
                    self.push_notification_description = f'{self.request.user} declined request to delete the Moogt Card, "{argument.moogt}" Waiting on {get_awaited_user(request.user, activity.user, argument.moogt)} to also vote.'
                elif activity.status == ActivityStatus.WAITING.value:
                    activity.status = action_type
                    activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    activity.save()
                    verb = "declined"

                    self.push_notification_title = f'{self.request.user} Declined request to Delete Moogt'
                    self.push_notification_description = f'{self.request.user} declined your request to delete the Moogt, "{argument.moogt}"'
            else:
                verb = "declined"
                activity.status = action_type
                activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                activity.save()
                self.push_notification_title = f'{self.request.user} Declined request to Delete Moogt'
                self.push_notification_description = f'{self.request.user} declined your request to delete the Moogt, "{argument.moogt}"'

        elif action_type == ActivityStatus.CANCELLED.value:
            activity.status = action_type
            activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            activity.save()

            async_to_sync(notify_ws_clients_for_argument)(activity.argument,
                                                          MoogtWebsocketMessageType.ARGUMENT_DELETE_CANCELLED.value)
        if verb:
            self.send_argument_request_resolved_notifications(
                argument, activity, verb, push_notification_title, push_notification_description, include_argument=notification_include_argument)

        return Response(self.get_serializer(activity).data, status.HTTP_200_OK)


class EditRequestActionApiView(ActivityActionValidationMixin,
                               SerializerExtensionsAPIViewMixin,
                               generics.GenericAPIView):
    serializer_class = ArgumentActivitySerializer

    def post(self, request, *args, **kwargs):
        activity_id = request.data.pop("activity_id", None)

        if activity_id is None:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not make an edit action request with no activity id.")
#
        activity = get_object_or_404(ArgumentActivity, pk=activity_id)
        verb = None

        if activity.type != ArgumentActivityType.EDIT.value:
            raise rest_framework.exceptions.ValidationError(
                "This endpoint is to take action only on editing a card")

        action_type = self.validate(activity)

        argument = activity.argument
        push_notification_title = 'You have a new Notification'
        push_notification_description = 'You have a new Notification'

        if action_type == ActivityStatus.ACCEPTED.value:
            # Edit The argument
            edited = get_object_or_404(Argument, pk=argument.modified_child.pk)
            verb = "accepted"

            push_notification_title = f'{self.request.user} Approved request to Edit Moogt Card'
            push_notification_description = f'{self.request.user} approved your request to Edit Moogt Card, "{argument.moogt}"'

            argument.is_removed = False
            argument.argument = edited.argument
            argument.modified_child = None
            argument.is_edited = True
            argument.save()

            edited.delete()

            activity.status = ActivityStatus.ACCEPTED.value
            activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.approve)
            activity.save()

            async_to_sync(notify_ws_clients_for_argument)(activity.argument,
                                                          MoogtWebsocketMessageType.ARGUMENT_EDIT_APPROVED.value)

        elif action_type == ActivityStatus.DECLINED.value:
            if argument.moogt.get_moderator():
                if activity.status == ActivityStatus.PENDING.value:
                    activity.status = ActivityStatus.WAITING.value

                    activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.waiting)
                    activity.save()

                    verb = "waiting"

                    self.push_notification_title = f'{self.request.user} declined request to Edit Moogt Card - Waiting on {get_awaited_user(request.user, activity.user,argument.moogt )}'
                    self.push_notification_description = f'{self.request.user} declined request to edit the Moogt Card, "{argument.moogt}" Waiting on {get_awaited_user(request.user, activity.user, argument.moogt)} to also vote.'
                elif activity.status == ActivityStatus.WAITING.value:
                    activity.status = action_type
                    activity.actions.create(
                        actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                    activity.save()

                    # argument.modified_child.delete()
                    argument.modified_child = None
                    argument.save()

                    verb = "declined"

                    self.push_notification_title = f'{self.request.user} Declined request to Edit Moogt'
                    self.push_notification_description = f'{self.request.user} declined your request to edit the Moogt, "{argument.moogt}"'

            else:
                verb = "declined"
                activity.status = action_type
                activity.actions.create(
                    actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.decline)
                activity.save()

                # Do not Edit the argument
                argument.modified_child.delete()
                argument.modified_child = None
                argument.save()

                self.push_notification_title = f'{self.request.user} Declined request to Edit Moogt Card'
                self.push_notification_description = f'{self.request.user} declined your request to edit the Moogt Card, "{argument.moogt}"'

        elif action_type == ActivityStatus.CANCELLED.value:
            activity.status = action_type
            activity.actions.create(
                actor=request.user, action_type=AbstractActivityAction.ACTION_TYPES.cancel)
            activity.save()

            argument.modified_child.delete()
            argument.modified_child = None
            argument.save()

            async_to_sync(notify_ws_clients_for_argument)(activity.argument,
                                                          MoogtWebsocketMessageType.ARGUMENT_EDIT_CANCELLED.value)

        if verb:
            self.send_argument_request_resolved_notifications(
                argument, activity, verb, push_notification_title, push_notification_description)

        return Response(self.get_serializer(activity).data, status.HTTP_200_OK)


class ArgumentDetailApiView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView):
    serializer_class = ArgumentSerializer
    extensions_exclude = {'moogt__stats', }
    extensions_expand = {'moogt', 'moogt__banner', 'reply_to__images'}.union(
        BasicArgumentSerializerExtensions.extensions_expand)

    def get(self, request, *args, **kwargs):
        argument = get_object_or_404(Argument.all_objects, pk=kwargs.get('pk'))

        if argument.is_removed:
            return Response(status=status.HTTP_204_NO_CONTENT)

        argument = get_object_or_404(
            Argument.objects.prefetch_related_objects(), pk=argument.id)
        return Response(self.get_serializer(argument).data, status.HTTP_200_OK)


class AdjacentArgumentsListApiView(SerializerExtensionsAPIViewMixin, generics.GenericAPIView,
                                   BasicArgumentSerializerExtensions):
    serializer_class = ArgumentSerializer

    def get(self, request, *args, **kwargs):
        argument = get_object_or_404(Argument, pk=kwargs.get('pk'))

        all_arguments = argument.moogt.arguments.prefetch_related_objects().order_by(
            'created_at').filter(Q(type=ArgumentType.NORMAL.name) | Q(type=ArgumentType.MODERATOR_ARGUMENT.name))

        before = all_arguments.filter(
            created_at__lt=argument.created_at
        )
        after = all_arguments.filter(
            created_at__gt=argument.created_at
        )

        if argument == all_arguments.first():
            return Response(self.get_response(None, after[:2], before.count(), after.count()))

        if argument == all_arguments.last():
            return Response(
                self.get_response(reversed(before.reverse()[:2]), None, before.count(), after.count()))

        return Response(
            self.get_response(before.reverse()[:1], after[:1], before.count(), after.count()))

    def get_response(self, before_qs, after_qs, before_count, after_count):
        return {
            'prev_count': before_count,
            'prev_results': self.get_serializer(before_qs,
                                                many=True).data if before_qs else [],
            'next_count': after_count,
            'next_results': self.get_serializer(after_qs,
                                                many=True).data if after_qs else []
        }


class UploadArgumentImageApiView(generics.CreateAPIView):
    serializer_class = ArgumentImageSerializer


class ReadArgumentApiView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        moogt = request.data.get('moogt_id')
        moogt: Moogt = get_object_or_404(Moogt, pk=moogt)

        if not moogt:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not read a moogt with no moogt id.")

        if not moogt in request.user.following_moogts.all():
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not read a moogt with you don't follow.")

        read_by = request.user.read_moogts.filter(moogt=moogt).first()
        argument_id = request.data.get('latest_read_argument_id')
        argument = get_object_or_404(Argument, pk=argument_id)

        if read_by and read_by.latest_read_at < argument.created_at:
            read_by.latest_read_at = argument.created_at
            read_by.save()

        return Response(data={}, status=status.HTTP_200_OK)


class ReportArgumentApiView(ReportMixin, generics.CreateAPIView):
    serializer_class = ArgumentReportSerializer

    def post(self, request, *args, **kwargs):
        argument_id = kwargs.get('pk')
        self.argument = get_object_or_404(Argument, pk=argument_id)

        self.validate(created_by=self.argument.user,
                      reported_by=request.user, queryset=self.argument.reports.all())

        return super().post(request, args, kwargs)

    def perform_create(self, serializer):
        report = serializer.save(
            reported_by=self.request.user, argument=self.argument)
        self.notify_admins(report)
