from django.db.models import Prefetch, Q
from django_comments_xtd.models import XtdComment, ContentType
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin

from api.enums import ReactionType, ViewType, Visibility
from api.serializers import TagSerializer, StatsItemSerializer, ReactionStatsSerializer, BaseViewArgumentSerializer
from arguments.models import Argument
from arguments.serializers import ArgumentSerializer
from users.models import MoogtMedaUser
from users.serializers import MoogtMedaUserSerializer
from views.models import ViewReport, ViewStats, ViewImage, View


# This Serializer is no longer needed, check for usage and this can be deleted.


class ViewStatsSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    applaud = SerializerMethodField()
    endorse = SerializerMethodField()
    disagree = SerializerMethodField()
    comment = SerializerMethodField()
    share_count = SerializerMethodField()

    class Meta:
        model = ViewStats
        fields = ['applaud', 'share_count', 'endorse', 'disagree', 'comment']

    def get_applaud(self, view_stats):
        selected = None
        if self.context.get('request').user.is_authenticated:
            selected = view_stats.applauds.filter(
                pk=self.context['request'].user.pk).exists()

        return self.get_stat_dict(view_stats.applauds.all().count(),
                                  selected,
                                  True)

    def get_endorse(self, view_stats):
        query = self.get_view_reactions_query(
            view_stats.view, ReactionType.ENDORSE.name)

        count = query.count()
        selected = None
        if self.context.get('request').user.is_authenticated:
            selected = query.filter(user=self.context['request'].user).exists()
        allowed = not self.get_view_reactions_by_user(view_stats.view,
                                                      ReactionType.DISAGREE.name,
                                                      self.context['request'].user).filter(
            content__isnull=True).exists()

        return self.get_stat_dict(count, selected, allowed)

    def get_disagree(self, view_stats):
        query = self.get_view_reactions_query(
            view_stats.view, ReactionType.DISAGREE.name)

        count = query.count()
        selected = None
        if self.context.get('request').user.is_authenticated:
            selected = query.filter(user=self.context['request'].user).exists()
        allowed = not self.get_view_reactions_by_user(
            view_stats.view,
            ReactionType.ENDORSE.name,
            self.context['request'].user
        ).filter(content__isnull=True).exists()

        return self.get_stat_dict(count, selected, allowed)

    def get_comment(self, view_stats):
        # TODO: This should return the actual number of comments
        return 1000

    def get_share_count(self, view_stats):
        return view_stats.func_get_share_count()

    def get_view_reactions_by_user(self, view, reaction_type, user):
        return self.get_view_reactions_query(view, reaction_type).filter(user=user)

    @staticmethod
    def get_view_reactions_query(view, reaction_type):
        return view.view_reactions.filter(type=ViewType.VIEW_REACTION.name,
                                          reaction_type=reaction_type)

    @staticmethod
    def get_stat_dict(count, selected, allowed):
        return {
            'count': count,
            'selected': selected,
            'allowed': allowed
        }


class ViewImageSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    class Meta:
        model = ViewImage
        fields = ['id', 'image']


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    can_follow = serializers.BooleanField()
    followers_count = serializers.IntegerField()
    is_following = serializers.BooleanField()

    @staticmethod
    def is_user_in_followers_list(user, followers):
        return any(f.id == user.id for f in followers)


class ViewNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    class Meta:
        model = View
        fields = ['id', 'content']
        expandable_fields = dict(
            user=dict(
                serializer=MoogtMedaUserSerializer,
                read_only=True
            ),
        )


class ViewSerializer(SerializerExtensionsMixin, serializers.ModelSerializer, BaseViewArgumentSerializer):
    parent = SerializerMethodField()
    stats = SerializerMethodField()
    is_parent_visible = SerializerMethodField()
    top_reaction = SerializerMethodField()
    my_top_reaction = SerializerMethodField()
    total_reactions = SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)

    @staticmethod
    def publicity_filter(queryset, user_id):

        filter = Q(is_hidden=False, visibility=Visibility.PUBLIC.name)

        if user_id:
            user = MoogtMedaUser.objects.prefetch_related(
                Prefetch('followings')).get(pk=user_id)
            following_ids = [
                following.pk for following in user.followings.all()] + [user.pk]
            filter = Q(visibility=Visibility.FOLLOWERS_ONLY.name, user__pk__in=following_ids, is_hidden=False) | \
                Q(is_hidden=False, visibility=Visibility.PUBLIC.name)

        queryset = queryset.filter(filter)

        return queryset

    class Meta:
        model = View
        fields = ['id', 'content', 'visibility', 'created_at', 'user', 'user_id',
                  'is_hidden', 'is_comment_disabled', 'is_edited', 'type', 'is_draft',
                  'reaction_type', 'parent', 'stats', 'is_comment_disabled', 'is_parent_visible',
                  'top_reaction', 'my_top_reaction', 'total_reactions']
        expandable_fields = dict(
            tags=dict(serializer=TagSerializer, many=True),
            images=dict(
                serializer=ViewImageSerializer,
                read_only=True,
                many=True
            ),

            parent_argument=dict(
                serializer=ArgumentSerializer,
                read_only=True
            )
        )

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return View.objects.create(**validated_data)

    def update(self, view, validated_data):
        # Remove all tags and images from the view.

        images = self.context['request'].data.pop(
            'images') if 'images' in self.context['request'].data else None
        tags = validated_data.pop('tags') if 'tags' in validated_data else None

        if images != None:
            view.images.clear()
            view.add_images(images)

        if tags != None:
            view.tags.clear()
            created_tags = View.objects.create_tags(tags)
            view.add_tags(created_tags)

        return super().update(view, validated_data)

    def validate(self, data):
        if 'images' not in self.context['request'].data and data.get('content', '') == "" \
                and self.context['is_update'] is False:
            raise serializers.ValidationError(
                'This view doesn\'t have any content')

        return data

    def get_is_parent_visible(self, view):
        parent = view.parent
        if not parent:
            return False
        user = parent.user

        if isinstance(parent, Argument):
            parent = parent.moogt

        if user == self.context['request'].user:
            return True

        return (parent.visibility == Visibility.FOLLOWERS_ONLY.name and
                self.context['request'].user in user.followers.all()) or \
            parent.visibility == Visibility.PUBLIC.name

    def get_parent(self, view):
        parent = view.parent
        if parent is not None and parent.is_removed:
            return None
        if isinstance(parent, View):
            context = {**self.context, 'only': {'id', 'content', 'visibility', 'created_at',
                                                'type', 'reaction_type', 'stats', 'user_id', 'user'}, 'expand': {'user', 'user__profile'}}
            if not self.get_is_parent_visible(view):
                parent.content = None

            return ViewSerializer(parent, context=context).data
        elif isinstance(parent, Argument):
            context = {**self.context,
                       'expand': {'user', 'user__profile'}, 'only': []}
            if not self.get_is_parent_visible(view):
                parent.argument = None
            return ArgumentSerializer(parent, context=context).data

    def get_stats(self, view):
        endorsements = getattr(view, 'endorsement_reactions', [])
        users_endorsing = self.get_users([e.user for e in endorsements])

        disagreements = getattr(view, 'disagreement_reactions', [])
        users_disagreeing = self.get_users([e.user for e in disagreements])

        applauds = getattr(view.stats, 'view_applauds', [])
        users_applauding = self.get_users(applauds)

        endorsements_count = len(users_endorsing)
        disagreements_count = len(users_disagreeing)
        total = endorsements_count + disagreements_count

        comments_count = view.comment_count

        ctype = ContentType.objects.get_for_model(view)
        curr_user = self.context['request'].user

        return {
            'endorse': ReactionStatsSerializer({
                'count': endorsements_count,
                'selected': self.has_user_reacted(curr_user, endorsements),
                'allowed': self.reaction_allowed(curr_user, endorsements, disagreements),
                'percentage': self.calculate_percentage(endorsements_count, total),
                'has_reaction_with_statement': self.has_reaction_with_statement(curr_user, endorsements)
            }).data,
            'disagree': ReactionStatsSerializer({
                'count': disagreements_count,
                'selected': self.has_user_reacted(curr_user, disagreements),
                'allowed': self.reaction_allowed(curr_user, disagreements, endorsements),
                'percentage': self.calculate_percentage(disagreements_count, total),
                'has_reaction_with_statement': self.has_reaction_with_statement(curr_user, disagreements)
            }).data,
            'applaud': StatsItemSerializer({
                'count': len(users_applauding),
                'selected': self.has_user_applauded(curr_user, applauds),
                'allowed': True,
            }).data,
            'comment': StatsItemSerializer({
                'count': comments_count,
                'selected': XtdComment.objects.filter(user_id=curr_user.id,
                                                      content_type=ctype,
                                                      object_pk=view.pk).exists(),
                'allowed': True,
            }).data
        }

    def get_top_reaction_dict(self, view, key):
        if (
                hasattr(view, f'{key}_content') and
                hasattr(view, f'{key}_user_id') and
                hasattr(view, f'{key}_reaction_type') and
                getattr(view, f'{key}_content') and
                getattr(view, f'{key}_user_id') and
                getattr(view, f'{key}_reaction_type')
        ):
            return {
                'content': getattr(view, f'{key}_content'),
                'user_id': getattr(view, f'{key}_user_id'),
                'reaction_type': getattr(view, f'{key}_reaction_type')
            }

    def get_top_reaction(self, view):
        return self.get_top_reaction_dict(view, 'top_reaction')

    def get_my_top_reaction(self, view):
        return self.get_top_reaction_dict(view, 'my_top_reaction')

    def get_total_reactions(self, view):
        if hasattr(view, 'total_reactions'):
            return view.total_reactions

class ViewReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ViewReport
        fields = ['id', 'link', 'reason', 'remark']