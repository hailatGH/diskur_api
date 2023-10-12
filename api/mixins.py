import json

import rest_framework
from django.core.mail import mail_admins
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django.db.models import ExpressionWrapper, F, FloatField, Count, Exists, \
    OuterRef, Q, DecimalField, DateTimeField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_comments_xtd.forms import XtdCommentForm
from django_comments_xtd.models import XtdComment
from django_comments_xtd.views import perform_like, perform_dislike
from django.template.loader import render_to_string
from open_facebook import OpenFacebook
from rest_framework.exceptions import ValidationError

from api.signals import reaction_was_made
from api.utils import get_admin_url
from arguments.models import Argument, ArgumentImage, ArgumentReactionType
from meda.enums import ActivityStatus
from meda.models import BaseReport, Score
from polls.models import Poll
from moogts.models import Moogt, MoogtActivity, MoogtActivityBundle, MoogtActivityType
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from users.models import MoogtMedaUser
from views.models import View, ViewImage
from .enums import ReactionType, ViewType, Visibility
from .expressions import Epoch


class CreateImageMixin(object):
    def create_image(self, obj):
        images = self.request.data.get('images')
        if images:
            if len(images) > 4:
                raise rest_framework.exceptions.ValidationError(
                    'You can upload max 4 images.')
            for image_id in images:
                if isinstance(obj, Argument):
                    image = get_object_or_404(ArgumentImage, pk=image_id)
                    image.argument = obj
                    image.save()
                elif isinstance(obj, View):
                    image = get_object_or_404(ViewImage, pk=image_id)
                    image.view = obj
                    image.save()


class ApplaudMixin(object):
    @staticmethod
    def maybe_applaud(obj, user):
        obj_stats = obj.stats
        has_applauded = False
        if not obj_stats.applauds.filter(id=user.id).exists():
            obj_stats.applauds.add(user)
            has_applauded = True
        else:
            obj_stats.applauds.remove(user)

        reaction_was_made.send(sender=__class__, obj=obj,
                               type=ReactionType.APPLAUD.name)
        return has_applauded


class HideMixin(object):
    @staticmethod
    def hide_unhide(obj):
        obj.is_hidden = not obj.is_hidden
        obj.save()


class UpdatePublicityMixin(object):
    def update_publicity(self, obj, visibility):
        if visibility != Visibility.FOLLOWERS_ONLY.name and visibility != Visibility.PUBLIC.name:
            raise ValidationError("Invalid visibility provided")

        obj.visibility = visibility
        obj.save()

        return obj


class ViewArgumentReactionMixin(CreateImageMixin, object):
    def get_reacting_users(self, request, obj):
        reaction_type = request.query_params.get('type')
        moogter_reactions = None
        user_query = MoogtMedaUser.objects.none()
        if reaction_type and reaction_type not in [ReactionType.ENDORSE.name,
                                                   ReactionType.DISAGREE.name,
                                                   ReactionType.APPLAUD.name]:
            raise ValidationError(
                f'{reaction_type} is an invalid query param.')

        if reaction_type in [ReactionType.ENDORSE.name, ReactionType.DISAGREE.name]:
            if isinstance(obj, Argument):
                reactions = obj.argument_reactions
                moogter_reactions = obj.moogter_reactions
            elif isinstance(obj, View):
                reactions = obj.view_reactions

            user_ids = reactions.filter(
                reaction_type=reaction_type).values_list('user', flat=True)

            if moogter_reactions:
                rxn_type = ArgumentReactionType.ENDORSEMENT.name if reaction_type == ReactionType.ENDORSE.name else ArgumentReactionType.DISAGREEMENT.name
                moogter_ids = moogter_reactions.filter(
                    reaction_type=rxn_type).values_list('user', flat=True)
                user_query = MoogtMedaUser.objects.filter(id__in=moogter_ids)

            queryset = MoogtMedaUser.objects.filter(
                id__in=user_ids) | user_query

        else:
            queryset = obj.stats.applauds.all()

        queryset = self.sort_by_follower_count_and_following_status(
            request, queryset)

        return queryset

    def react(self, request, obj, view_type):
        data = {
            'type': view_type,
            'content': request.data.get('content', None),
            'reaction_type': request.data['type'],
            'visibility': request.data.get('visibility', Visibility.PUBLIC.name),
            'tags': request.data.get('tags', []),
            'is_comment_disabled': request.data.get('is_comment_disabled', False)
        }

        if view_type == ViewType.VIEW_REACTION.name:
            data['parent_view'] = obj
        elif view_type == ViewType.ARGUMENT_REACTION.name:
            data['parent_argument'] = obj

        reaction_view = None

        # Make sure the object has no opposing reactions.
        if not self.has_opposing_reactions(obj, request.data['type'], view_type, request.user):
            # If reaction without statements exists, try update it or remove it.
            if self.has_reaction_without_statement(obj, request.data['type'], view_type, request.user):
                reaction_without_statement = self.get_reaction_without_statement(obj,
                                                                                 request.data['type'],
                                                                                 view_type,
                                                                                 request.user)
                # This means the reaction is to toggle your already existing reactions, i.e., remove it.
                if not request.data.get('content', None):
                    # remove the created notification
                    self.remove_notification(reaction_without_statement)
                    # remove the toggled reaction without statement
                    reaction_without_statement.delete()
                    if view_type == ViewType.ARGUMENT_REACTION.name and obj.moogt.get_opponent(
                            request.user) == obj.user:
                        # delete the status argument object if moogter is un-reacting to an argument of an opponent
                        MoogtActivity.objects.filter(moogt=obj.moogt,
                                                     user=request.user,
                                                     react_to=obj,
                                                     type=self.get_moogt_activity_reaction_type(
                                                         data['reaction_type'])).delete()
                else:
                    # Try to update your reaction.without statement, and it will have your statement.
                    self.create_image(reaction_without_statement)
                    reaction_view = self.update_a_view(
                        reaction_without_statement, data)

            elif self.has_reaction_with_statement(obj, request.data['type'], view_type, request.user) \
                    and not request.data.get('content', None):
                raise ValidationError(
                    "You can not react with out statement on a view that already has reaction with statements.")

            else:
                # If the reaction has no opposing reaction and no reaction without a statement,
                # Just create a new reaction view.
                reaction_view = self.create_a_view(data, request.user)
                if view_type == ViewType.ARGUMENT_REACTION.name and obj.moogt.get_opponent(request.user) == obj.user:
                    # create an activity object if moogter is reacting to an argument of an opponent
                    activity = MoogtActivity.objects.create(moogt=obj.moogt,
                                                            user=request.user,
                                                            status=ActivityStatus.ACCEPTED.value,
                                                            react_to=obj,
                                                            type=self.get_moogt_activity_reaction_type(
                                                                data['reaction_type']))
                    ActivityActionValidationMixin.create_or_update_bundle(
                        obj.moogt, activity)

        # The view has opposing reaction.
        else:
            opposing_reaction_type = self.get_opposing_reaction_type(
                request.data['type'])
            # Check if the object has an opposing reaction without a statement.
            if self.has_reaction_without_statement(obj, opposing_reaction_type, view_type, request.user):
                if request.data.get('content', None) is not None:
                    raise ValidationError(
                        f"There is an existing {request.data.get('type')} without statement reaction that \
                            has to be toggled first to make this request.")

                opp_rxn_without_statement = self.get_reaction_without_statement(obj,
                                                                                opposing_reaction_type,
                                                                                view_type,
                                                                                request.user)

                # delete notification for opposing reaction with statement
                self.remove_notification(
                    opp_rxn_without_statement, opposite=True)
                # Toggle the opposing reaction without statement and create one with opposing type
                opp_rxn_without_statement.delete()

                # if user is a moogter toggle the MoogtActivity creation
                if view_type == ViewType.ARGUMENT_REACTION.name and obj.moogt.get_opponent(request.user) == obj.user:
                    MoogtActivity.objects.filter(moogt=obj.moogt,
                                                 user=request.user,
                                                 react_to=obj,
                                                 type=self.get_moogt_activity_reaction_type(
                                                     opposing_reaction_type)).delete()

                    activity = MoogtActivity.objects.create(moogt=obj.moogt,
                                                            user=request.user,
                                                            status=ActivityStatus.ACCEPTED.value,
                                                            react_to=obj,
                                                            type=self.get_moogt_activity_reaction_type(
                                                                data['reaction_type']))
                    ActivityActionValidationMixin.create_or_update_bundle(
                        obj.moogt, activity)

            # check if the object has opposing reactions but they are not reaction without statement
            # and there is no content provided
            elif not request.data.get('content', None):
                # You must provide a statement if a view has an opposing reaction.
                raise ValidationError(
                    f"You must provide a statement to your {request.data.get('type')} reaction.")

            # Create a new reaction view as well.
            reaction_view = self.create_a_view(data, request.user)

        if isinstance(obj, Argument):
            self.update_argument(obj)

        reaction_was_made.send(__class__, obj=obj, type=request.data['type'])

        return reaction_view

    @staticmethod
    def get_opposing_reaction_type(reaction_type):
        return ReactionType.DISAGREE.name if reaction_type == ReactionType.ENDORSE.name else ReactionType.ENDORSE.name

    @staticmethod
    def has_opposing_reactions(obj, reaction_type, view_type, user):
        opposing_reaction_type = ViewArgumentReactionMixin.get_opposing_reaction_type(
            reaction_type)
        if view_type == ViewType.VIEW_REACTION.name:
            return obj.view_reactions.filter(reaction_type=opposing_reaction_type, user=user).count() > 0
        elif view_type == ViewType.ARGUMENT_REACTION.name:
            return obj.argument_reactions.filter(reaction_type=opposing_reaction_type, user=user).count() > 0

    @staticmethod
    def has_reaction_without_statement(obj, reaction_type, view_type, user):
        return ViewArgumentReactionMixin.reaction_without_statement_query(obj, reaction_type,
                                                                          view_type,
                                                                          user).count() > 0

    @staticmethod
    def has_reaction_with_statement(obj, reaction_type, view_type, user):
        return ViewArgumentReactionMixin.reaction_with_statement_query(obj, reaction_type, view_type, user).count() > 0

    @staticmethod
    def get_reaction_without_statement(obj, reaction_type, view_type, user):
        return ViewArgumentReactionMixin.reaction_without_statement_query(obj, reaction_type, view_type, user).first()

    @staticmethod
    def reaction_without_statement_query(obj, reaction_type, view_type, user):
        if view_type == ViewType.VIEW_REACTION.name:
            return obj.view_reactions.filter(type=view_type,
                                             content__isnull=True,
                                             reaction_type=reaction_type,
                                             user=user)
        elif view_type == ViewType.ARGUMENT_REACTION.name:
            return obj.argument_reactions.filter(type=view_type,
                                                 content__isnull=True,
                                                 reaction_type=reaction_type,
                                                 user=user)

    @staticmethod
    def get_notification_types(rxn_without_statement):
        if rxn_without_statement.type == ViewType.VIEW_REACTION.name:
            if rxn_without_statement.reaction_type == ReactionType.ENDORSE.name:
                return NOTIFICATION_TYPES.view_agree
            elif rxn_without_statement.reaction_type == ReactionType.DISAGREE.name:
                return NOTIFICATION_TYPES.view_disagree
        elif rxn_without_statement.type == ViewType.ARGUMENT_REACTION.name:
            if rxn_without_statement.reaction_type == ReactionType.ENDORSE.name:
                return NOTIFICATION_TYPES.argument_agree
            elif rxn_without_statement.reaction_type == ReactionType.DISAGREE.name:
                return NOTIFICATION_TYPES.argument_disagree

    def remove_notification(self, rxn_without_statement, opposite=False):
        notification_type = self.get_notification_types(rxn_without_statement)

        Notification.objects.remove_notification(
            rxn_without_statement.parent,
            rxn_without_statement.user,
            notification_type)

    @staticmethod
    def get_moogt_activity_reaction_type(rxn_type):
        if rxn_type == ReactionType.ENDORSE.name:
            return MoogtActivityType.ENDORSEMENT.name
        return MoogtActivityType.DISAGREEMENT.name

    @staticmethod
    def reaction_with_statement_query(obj, reaction_type, view_type, user):
        if view_type == ViewType.VIEW_REACTION.name:
            return obj.view_reactions.filter(type=view_type,
                                             content__isnull=False,
                                             reaction_type=reaction_type,
                                             user=user)
        elif view_type == ViewType.ARGUMENT_REACTION.name:
            return obj.argument_reactions.filter(type=view_type,
                                                 content__isnull=False,
                                                 reaction_type=reaction_type,
                                                 user=user)

    @transaction.atomic
    def create_a_view(self, data, user):
        data['user'] = user
        view = View.objects.create(**data)
        self.create_image(view)
        self.send_notification(view)
        return view

    def send_notification(self, view: View):
        from views.serializers import ViewNotificationSerializer
        from arguments.serializers import ArgumentNotificationSerializer

        data = {'view': ViewNotificationSerializer(view).data}
        notification_type = None
        push_notification_title = 'You have new notification'
        push_notification_description = 'You have new notification'

        if view.parent_view:
            data['parent_view'] = ViewNotificationSerializer(
                view.parent_view).data
            parent = view.parent_view

            if view.reaction_type == ReactionType.ENDORSE.name:
                notification_type = NOTIFICATION_TYPES.view_agree
                verb = "agreed"
                if view.content == None:
                    push_notification_title = f'{self.request.user} Agreed with your View'
                    push_notification_description = f'{view.user} agreed with your view, "{view.parent_view}"'
                else:
                    push_notification_title = f'{self.request.user} Agreed with Statement'
                    push_notification_description = f'{view.user} agreed to your view, "{view.parent_view} with, "{view.content}"'

            elif view.reaction_type == ReactionType.DISAGREE.name:
                notification_type = NOTIFICATION_TYPES.view_disagree
                verb = "disagreed"
                if view.content == None:
                    push_notification_title = f'{self.request.user} Disagreed with your View'
                    push_notification_description = f'{view.user} disagreed with your view, "{view.parent_view}"'
                else:
                    push_notification_title = f'{self.request.user} Disagreed with Statement'
                    push_notification_description = f'{view.user} disagreed to your view, "{view.parent_view} with, "{view.content}"'

        elif view.parent_argument:
            data['parent_argument'] = ArgumentNotificationSerializer(
                view.parent_argument).data
            parent = view.parent_argument

            if view.reaction_type == ReactionType.ENDORSE.name:
                notification_type = NOTIFICATION_TYPES.argument_agree
                verb = "agreed"
                if view.content == None:
                    push_notification_title = f'{self.request.user} Agreed with your Card'
                    push_notification_description = f'{view.user} agreed with your card, "{parent}"'
                else:
                    push_notification_title = f'{self.request.user} Agreed with Statement'
                    push_notification_description = f'{view.user} agreed to your card, "{parent} with, "{view.content}"'

            elif view.reaction_type == ReactionType.DISAGREE.name:
                notification_type = NOTIFICATION_TYPES.argument_disagree
                verb = "disagreed"
                if view.content == None:
                    push_notification_title = f'{self.request.user} Disagreed with your Card'
                    push_notification_description = f'{view.user} disagreed with your card, "{parent}"'
                else:
                    push_notification_title = f'{self.request.user} Disagreed with Statement'
                    push_notification_description = f'{view.user} disagreed to your card, "{parent} with, "{view.content}"'

        if notification_type and parent.user != view.user:
            notify.send(recipient=parent.user,
                        sender=view.user,
                        verb=verb,
                        send_email=False,
                        send_telegram=True,
                        type=notification_type,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=parent,
                        data=data,
                        push_notification_title=push_notification_title,
                        push_notification_description=push_notification_description
                        )

    @staticmethod
    def update_a_view(view, data):
        view.content = data['content']

        tags = data.pop('tags') if 'tags' in data else []

        if tags:
            created_tags = View.objects.create_tags(tags)
            view.add_tags(created_tags)

        view.save()
        return view

    @staticmethod
    def update_argument(argument: Argument):
        argument: Argument = Argument.objects.annotate(
            end_count=Count('argument_reactions__user',
                            filter=Q(argument_reactions__reaction_type=ReactionType.ENDORSE.name,
                                     argument_reactions__is_removed=False),
                            distinct=True),
            dis_count=Count('argument_reactions__user',
                            filter=Q(argument_reactions__reaction_type=ReactionType.DISAGREE.name,
                                     argument_reactions__is_removed=False),
                            distinct=True)).get(pk=argument.pk)

        argument.stats.endorsement_count = argument.end_count
        argument.stats.disagreement_count = argument.dis_count
        argument.stats.save()

    @ staticmethod
    def sort_by_follower_count_and_following_status(request, queryset):

        subquery = request.user.followings.filter(id=OuterRef('pk'))

        queryset = queryset.annotate(
            # The number of followers for each individual user.
            followers_count=Count('follower'),
            followed=Exists(subquery)
        ).order_by('-followers_count', '-followed')

        return queryset


class TrendingMixin(object):
    # This is to limit the trending items.
    TRENDING_LIMIT = 100

    def get_trending_factor_queryset(self, queryset):
        # This is used for getting the score of the item and the result will be a FloatField type.
        score_expression = ExpressionWrapper(F('score__score_now') - F('score__score_before'),
                                             output_field=FloatField())

        # Annotate each view with a trending_factor field and use that to sort the views in reverse order.
        # The trending_factor is the rate of change of score over a certain period of time.
        # A higher trending_score means a view is trending.
        trending_queryset = queryset.annotate(
            trending_factor=ExpressionWrapper(
                score_expression * 1.0 / Score.TRENDING_DURATION_HOURS,
                output_field=FloatField()
            )
        ).filter(
            score__score_now__gte=Score.TRENDING_MINIMUM_SCORE
        ).order_by('-trending_factor')

        return trending_queryset[:self.TRENDING_LIMIT]

    def get_overall_score_trending_factor_queryset(self, queryset):
        duration = Epoch((F('now') - F('created_at')))

        queryset = queryset.annotate(
            now=Cast(timezone.now(), DateTimeField()),
            duration=duration,
            trending_factor=ExpressionWrapper(
                # the 10 ^ 6 * 3600 * 24 * 30 multiplication is to convert micro second duration to months
                (F('score__overall_score') * 1_000_000 * \
                 3600 * 24 * 30) / F('duration'),
                output_field=DecimalField()
            )).order_by(F('trending_factor').desc(nulls_last=True))

        return queryset

    def sort_queryset_by_popularity(self, queryset):
        return queryset.order_by(F('score__overall_score').desc(nulls_last=True))


class ShareMixin(object):

    def share(self, request):
        url = request.data.get('url')
        if not url:
            raise ValidationError('Url is required.')

        facebook = OpenFacebook(settings.FACEBOOK_AUTH_TOKEN)
        result = facebook.get('', id=url, fields='engagement')
        return result['engagement']['share_count']


class BrowseReactionsMixin(object):
    def get_reactions_queryset(self, queryset):
        # Get the reaction type from the query param, if it exists.
        reaction_type = self.request.query_params.get('type', None)
        if reaction_type in [ReactionType.ENDORSE.name, ReactionType.DISAGREE.name]:
            queryset = queryset.filter(reaction_type=reaction_type)

        # This means the request is to get only your own reactions.
        own_only = json.loads(self.request.query_params.get('own', 'false'))
        if self.request.user.is_authenticated and own_only:
            return queryset.filter(user=self.request.user)

        # If user is authenticated, exclude his/her own reactions.
        if self.request.user.is_authenticated:
            queryset = queryset.exclude(user=self.request.user)

        return queryset


class CommentMixin(object):
    def comment(self, request, obj):
        data = request.data
        data['name'] = request.user.first_name
        data['email'] = request.user.email
        data['honeypot'] = ''
        data['thread_id'] = obj.pk

        form = XtdCommentForm(obj)
        security_data = form.generate_security_data()
        data.update(security_data)

        serializer = self.get_serializer(data=data)
        if serializer.is_valid(raise_exception=True):
            comment = serializer.save()
            reaction_was_made.send(sender=__class__, obj=obj)
            return comment['comment'].xtd_comment
        return serializer.data

    def get_comments(self, request, obj):
        content_type = ContentType.objects.get_for_model(obj)

        return XtdComment \
            .objects \
            .filter(
                content_type=content_type,
                object_pk=obj.pk,
                site__pk=get_current_site(request).pk,
                is_public=True,
                is_removed=False
            ).order_by('-submit_date').select_related('user', 'user__profile')

    def like_comment(self, request, comment):
        from .serializers import CommentNotificationSerializer

        liked = perform_like(request, comment)

        if isinstance(comment.content_object, XtdComment):
            data = {
                'original': CommentNotificationSerializer(comment.content_object, context={'request': request}).data,
                'comment': CommentNotificationSerializer(comment, context={'request': request}).data,
            }
        else:
            data = {
                'original': CommentNotificationSerializer(comment, context={'request': request}).data
            }

        if isinstance(comment.content_object, Argument):
            push_notification_description = f'{request.user} applauded your Comment,"{comment.comment}" on the Moogt Card, "{comment.content_object}"'
        elif isinstance(comment.content_object, View):
            push_notification_description = f'{request.user} applauded your Comment,"{comment.comment}" on the View, "{comment.content_object}"'
        elif isinstance(comment.content_object, Poll):
            push_notification_description = f'{request.user} applauded your Comment,"{comment.comment}" on the Poll, "{comment.content_object}"'
        else:
            push_notification_description = f'{request.user} applauded your Comment,"{comment.comment}"'

        if liked and request.user != comment.user:
            notify.send(
                recipient=comment.user,
                sender=self.request.user,
                verb="applauded",
                target=comment,
                send_email=False,
                send_telegram=True,
                type=NOTIFICATION_TYPES.comment_applaud,
                data=data,
                push_notification_title=f'{self.request.user} Applauded your Comment!',
                push_notification_description=push_notification_description)
        elif not liked and request.user != comment.user:
            Notification.objects.remove_notification(
                comment,
                request.user,
                NOTIFICATION_TYPES.comment_applaud
            )
        return liked

    def unlike_comment(self, request, comment):
        return perform_dislike(request, comment)


class ActivityActionValidationMixin(object):
    def send_notification(self, recipient, moogt, verb, notification_type, push_notification_description, push_notification_title, data=None):
        notify.send(
            recipient=recipient,
            sender=self.request.user,
            verb=verb,
            target=moogt,
            send_email=False,
            send_telegram=True,
            type=notification_type,
            data=data,
            push_notification_title=push_notification_title,
            push_notification_description=push_notification_description
        )

    @ staticmethod
    def create_or_update_bundle(moogt, moogt_activity):
        latest_bundle = moogt.bundles.last()

        if latest_bundle and \
                not moogt.arguments.filter(created_at__gt=latest_bundle.created_at).exists() and \
                not moogt.statuses.filter(created_at__gt=latest_bundle.created_at).exists():
            # if the latest object is bundle update the bundle with the new activity
            moogt_activity.bundle = latest_bundle
            moogt_activity.save()

            return latest_bundle
        else:
            # create a new bundle
            bundle = MoogtActivityBundle(moogt=moogt)
            bundle.save()

            moogt_activity.bundle = bundle
            moogt_activity.save()

            return bundle

    def __can_take_action(self, activity):
        participants = [activity.user]
        participants += list(map(lambda a: a.actor, activity.actions.all()))

        return self.request.user not in participants

    def validate(self, activity):
        activity_status = self.request.data.get('status')
        if not activity_status:
            raise ValidationError('You must provide the status.')

        if isinstance(activity, MoogtActivity):
            moogt: Moogt = activity.moogt
        else:
            moogt: Moogt = activity.argument.moogt

        if moogt.get_opposition() != self.request.user and moogt.get_proposition() != self.request.user and moogt.get_moderator() != self.request.user:
            raise rest_framework.exceptions.PermissionDenied(
                "Sorry you can not perform this action on a moogt you are not participating on")

        if activity.user == self.request.user and activity_status != ActivityStatus.DECLINED.value:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not perform this action on your own request.")

        if activity.user == self.request.user and activity_status == ActivityStatus.DECLINED.value:
            activity_status = ActivityStatus.CANCELLED.value

        if not self.__can_take_action(activity) and activity_status == ActivityStatus.ACCEPTED.value:
            raise rest_framework.exceptions.ValidationError("Sorry you can not perform action on a moogt " +
                                                            "that you are not opponent on")

        if activity.status != ActivityStatus.PENDING.value and activity.status != ActivityStatus.WAITING.value:
            raise rest_framework.exceptions.ValidationError(
                "Sorry you can not perform action ")

        return activity_status

    def send_argument_request_resolved_notifications(self, argument, activity, verb, push_notification_title,
                                                     push_notification_description, include_argument=True):
        from arguments.serializers import ArgumentNotificationSerializer, ArgumentActivitySerializer

        data = {'activity': ArgumentActivitySerializer(activity).data}
        if include_argument:
            data['argument'] = ArgumentNotificationSerializer(argument).data

        recipient = []

        if self.request.user == argument.moogt.get_proposition():
            recipient = [argument.moogt.get_opposition(),
                         argument.moogt.get_moderator()]

        elif self.request.user == argument.moogt.get_opposition():
            recipient = [argument.moogt.get_proposition(),
                         argument.moogt.get_moderator()]

        elif self.request.user == argument.moogt.get_moderator():
            recipient = [argument.moogt.get_proposition(),
                         argument.moogt.get_opposition()]

        filtered_recipient = list(filter(lambda rec: (rec != None), recipient))

        notify.send(
            recipient=filtered_recipient,
            sender=self.request.user,
            verb=verb,
            send_email=False,
            type=NOTIFICATION_TYPES.argument_request_resolved,
            send_telegram=True,
            target=argument,
            data=data,
            push_notification_title=push_notification_title,
            push_notification_description=push_notification_description
        )


class ActivityCreationValidationMixin(object):
    def validate(self, obj, activity_type=None):
        if isinstance(obj, Argument):
            self.validate_argument(obj, activity_type)
        elif isinstance(obj, Moogt):
            self.validate_moogt(obj, activity_type)

    def validate_argument(self, argument, activity_type):
        if not argument.moogt.func_is_participant(self.request.user):
            raise rest_framework.exceptions.ValidationError(
                "Users can not make a request on a moogt they are not participating")

        if argument.activities.filter(type=activity_type, status=ActivityStatus.PENDING.value).exists():
            raise rest_framework.exceptions.PermissionDenied(
                'There is an unresolved request on this type of request')

        if argument.user != self.request.user and self.request.user != argument.moogt.get_moderator():
            raise rest_framework.exceptions.ValidationError(
                "Users can not make a request on an argument they haven't created.")

    def validate_moogt(self, moogt, activity_type):
        if moogt.activities.filter(type=activity_type, status=ActivityStatus.PENDING.value).exists():
            raise rest_framework.exceptions.PermissionDenied(
                'There is an unresolved request on this type of request')

        if not moogt.func_is_participant(self.request.user):
            raise rest_framework.exceptions.PermissionDenied(
                'Users can not make a request on a moogt they are not participating.')

    def perform_create_with_notifications_moogt(self, serializer):
        from moogts.serializers import MoogtNotificationSerializer
        serializer.save()

        notify.send(
            recipient=MoogtMedaUser.objects.filter(
                id=self.moogt.get_opponent(self.request.user).pk),
            sender=self.request.user,
            verb=self.verb,
            send_email=False,
            type=NOTIFICATION_TYPES.moogt_request,
            send_telegram=True,
            target=self.moogt,
            data={'activity': serializer.data,
                  'moogt': MoogtNotificationSerializer(self.moogt).data},
            push_notification_title=self.push_notification_title,
            push_notification_description=self.push_notification_description
        )

    def send_argument_request_notifications(self, argument, activity, verb):
        from arguments.serializers import ArgumentNotificationSerializer, ArgumentActivitySerializer

        recipient = []

        if self.request.user == argument.moogt.get_proposition():
            recipient = [argument.moogt.get_opposition(),
                         argument.moogt.get_moderator()]

        elif self.request.user == argument.moogt.get_opposition():
            recipient = [argument.moogt.get_proposition(),
                         argument.moogt.get_moderator()]

        elif self.request.user == argument.moogt.get_moderator():
            recipient = [argument.moogt.get_proposition(),
                         argument.moogt.get_opposition()]

        filtered_recipient = list(filter(lambda rec: (rec != None), recipient))

        notify.send(
            recipient=filtered_recipient,
            sender=self.request.user,
            verb=verb,
            send_email=False,
            type=NOTIFICATION_TYPES.argument_request,
            send_telegram=True,
            target=argument,
            data={'activity': ArgumentActivitySerializer(activity).data,
                  'argument': ArgumentNotificationSerializer(argument).data},
            push_notification_title=self.push_notification_title,
            push_notification_description=self.push_notification_description
        )


class SortCategorizeFilterMixin(TrendingMixin):
    def sort_arguments(self, queryset, search_term=None, sort_by='date'):
        """
        This function helps to :
        filter by search_term, and sort using sort_by
        """
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        if sort_by == "date":
            queryset = queryset.order_by('-created_at')
        elif sort_by == 'popularity':
            queryset = self.sort_queryset_by_popularity(queryset)

        return queryset

    def categorize_and_sort_polls(self, queryset, search_term=None, sort_by='date', category='live'):
        """
        This function helps to:
        categorize views, filter by search_term, and sort using sort_by
        """
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        if category == 'live':
            queryset = queryset.get_live_polls()

        if category == 'closed':
            queryset = queryset.get_closed_polls()

        if sort_by == "date":
            queryset = queryset.order_by('-created_at')
        else:
            queryset = self.get_trending_factor_queryset(queryset)

        return queryset

    def categorize_and_sort_moogts(self, queryset, search_term=None, sort_by='date', category='live'):
        """
        This function helps to:
        categorize moogts, filter by search_term, sort using sort_by
        """
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        if category == 'live':
            queryset = queryset.get_live_moogts()

        elif category == 'premiering':
            queryset = queryset.filter(
                is_premiering=True, premiering_date__isnull=False)

        elif category == 'ended':
            queryset = queryset.get_ended_moogts()

        elif category == 'paused':
            queryset = queryset.get_paused_moogts()

        if sort_by == "date":
            queryset = queryset.order_by("-created_at")
        elif sort_by == 'popularity':
            queryset = queryset.order_by('-followers_count')

        return queryset

    def categorize_and_sort_views(self, queryset, search_term, sort_by='date', category='view'):
        """
        This function helps to:
        categorize views, filter by search_term, sort using sort_by
        """
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        if category == 'view':
            queryset = queryset.get_normal_views()

        if category == 'reaction_view':
            queryset = queryset.get_reaction_views()

        if category == 'reaction':
            queryset = queryset.get_one_time_reactions()

        if sort_by == "date":
            return queryset.order_by("-created_at")
        elif sort_by == 'trending':
            return self.get_trending_factor_queryset(queryset)
        elif sort_by == 'popularity':
            return self.sort_queryset_by_popularity(queryset)

        return queryset

    def categorize_and_sort_users(self, queryset, search_term, sort_by='date', category='subscribed'):
        """
        This function helps to:
        categorize users(accounts), filter by search_term, sort using sort_by
        """
        if search_term:
            queryset = queryset.filter_using_search_term(search_term)

        if self.request.user:
            subquery = self.request.user.followings.filter(id=OuterRef('pk'))
            queryset = queryset.annotate(follows_user=Exists(subquery))
            if category == 'subscribed':
                queryset = queryset.filter(follows_user=True)
            elif category == 'unsubscribed':
                queryset = queryset.filter(follows_user=False)

        if sort_by == 'date':
            queryset = queryset.order_by('-date_joined')
        elif sort_by == 'popularity':
            queryset = queryset.order_by('-followers_count')

        return queryset


class ReportMixin(object):
    def _validate_users(self, created_by: MoogtMedaUser, reported_by: MoogtMedaUser):
        if created_by == reported_by:
            raise rest_framework.exceptions.ValidationError(
                'You cannot report an item you created!')

    def _validate_duplicate_report(self, queryset, reported_by):
        queryset_count = queryset.filter(reported_by=reported_by).count()
        if queryset_count > 0:
            raise rest_framework.exceptions.ValidationError(
                'You cannot make a duplicate report!')

    def validate(self, created_by: MoogtMedaUser, reported_by: MoogtMedaUser, queryset):
        self._validate_users(created_by=created_by, reported_by=reported_by)
        self._validate_duplicate_report(
            reported_by=reported_by, queryset=queryset)

    def notify_admins(self, report: BaseReport):
        context = {
            'reported_by': report.reported_by,
            'reported_on': report.reported_on(),
            'created_at': report.item_created_at(),
            'reported_at': report.created_at,
            'reason': report.reason,
            'link': report.link,
            'report_link': get_admin_url(report),
            'protocol': self.request.scheme,
            'domain': self.request.get_host(),
        }
        msg_plain = render_to_string(
            'meda/report_email.txt')
        msg_html = render_to_string(
            'meda/report_email.html', context)
        mail_admins('Report on an item', message=msg_plain,
                    html_message=msg_html, fail_silently=False)
