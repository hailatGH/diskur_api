from django.contrib.contenttypes.models import ContentType
from django_comments_xtd.api.frontend import commentbox_props
from django_comments_xtd.api.serializers import ReadCommentSerializer
from django_comments_xtd.models import XtdComment
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField, IntegerField, DateTimeField
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin

from api.enums import ReactionType
from api.serializers import StatsItemSerializer, ReactionStatsSerializer, BaseViewArgumentSerializer
from arguments.models import Argument, ArgumentActivity, ArgumentActivityAction, ArgumentImage, ArgumentReport
from moogts.models import MoogtStatus, MoogtActivityBundle
from users.serializers import MoogtMedaUserSerializer
from views.models import View


class ArgumentNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    class Meta:
        model = Argument
        fields = ['id', 'argument']
        expandable_fields = dict(
            user=dict(serializer=MoogtMedaUserSerializer, read_only=True),
        )


class ArgumentSerializer(SerializerExtensionsMixin, serializers.ModelSerializer, BaseViewArgumentSerializer):
    stats = serializers.SerializerMethodField()
    proposition_created = serializers.SerializerMethodField()
    has_activities = serializers.SerializerMethodField()
    has_reactions = serializers.SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = Argument
        fields = ['id', 'argument', 'type', 'is_edited', 'has_activities',
                  'proposition_created', 'stats', 'reaction_type', 'created_at', 'updated_at',
                  'consecutive_expired_turns_count', 'has_reactions', 'user', 'user_id']
        expandable_fields = dict(

            moogt=dict(
                serializer='moogts.serializers.MoogtSerializer', read_only=True),
            reply_to=dict(
                serializer='arguments.serializers.ArgumentSerializer', read_only=True),
            modified_child=dict(
                serializer='arguments.serializers.ArgumentSerializer', read_only=True),
            react_to=dict(
                serializer='arguments.serializers.ArgumentSerializer', read_only=True),
            activities=dict(
                serializer='arguments.serializers.ArgumentActivitySerializer', many=True, read_only=True),
            images=dict(
                serializer='arguments.serializers.ArgumentImageSerializer', many=True, read_only=True)
        )

    def create(self, validated_data):
        argument = super().create(validated_data)
        argument.set_moogt(validated_data.get('moogt'))
        argument.set_user(validated_data.get('user'))
        argument.set_reply_to(validated_data.get('reply_to'))
        argument.set_react_to(validated_data.get('react_to'))
        argument.save()

        return argument

    def get_stats(self, argument):
        endorsements = getattr(argument, 'reactions', [])
        if len(endorsements) > 0:
            endorsements = list(
                filter(lambda x: (x.reaction_type == ReactionType.ENDORSE.name), endorsements))
        moogter_endorsements = getattr(
            argument, 'moogter_endorsement_reactions', [])
        users_endorsing = self.get_users(
            [e.user for e in [*endorsements, *moogter_endorsements]])

        disagreements = getattr(argument, 'reactions', [])
        if len(disagreements) > 0:
            disagreements = list(filter(lambda x: (
                x.reaction_type == ReactionType.DISAGREE.name), disagreements))
        moogter_disagreements = getattr(
            argument, 'moogter_disagreement_reactions', [])
        users_disagreeing = self.get_users(
            [e.user for e in [*disagreements, *moogter_disagreements]])

        applauds = getattr(argument.stats, 'argument_applauds', [])

        endorsements_count = len(users_endorsing)
        disagreements_count = len(users_disagreeing)
        total = endorsements_count + disagreements_count

        ctype = ContentType.objects.get_for_model(argument)
        current_user = self.context['request'].user

        return {
            'endorse': ReactionStatsSerializer({
                'count': endorsements_count,
                'selected': self.has_user_reacted(current_user, [*endorsements, *moogter_endorsements]),
                'allowed': self.reaction_allowed(current_user, endorsements, disagreements),
                'percentage': self.calculate_percentage(endorsements_count, total),
                'has_reaction_with_statement': self.has_reaction_with_statement(current_user, endorsements)
            }).data,
            'disagree': ReactionStatsSerializer({
                'count': disagreements_count,
                'selected': self.has_user_reacted(current_user, [*disagreements, *moogter_disagreements]),
                'allowed': self.reaction_allowed(current_user, disagreements, endorsements),
                'percentage': self.calculate_percentage(disagreements_count, total),
                'has_reaction_with_statement': self.has_reaction_with_statement(current_user, endorsements)
            }).data,
            'applaud': StatsItemSerializer({
                'count': len(applauds),
                'selected': self.has_user_applauded(current_user, applauds),
                'allowed': False,
            }).data,
            'comment': {**commentbox_props(argument, self.context['request'].user),
                        'count': argument.comment_count,
                        'selected': XtdComment.objects.filter(user_id=self.context['request'].user.id,
                                                              content_type=ctype,
                                                              object_pk=argument.pk).exists(),
                        'allowed': True
                        },
        }

    def get_proposition_created(self, argument):
        return argument.moogt.proposition == argument.user

    def get_has_activities(self, argument):
        return argument.activities.count() > 0

    def get_has_reactions(self, argument):
        has_reaction_views = getattr(argument, 'has_reaction_views', False)
        has_reaction_arguments = getattr(
            argument, 'has_reaction_arguments', False)

        return has_reaction_views or has_reaction_arguments


class ArgumentActivityActionSerializer(serializers.ModelSerializer):
    actor = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        fields = ['id', 'created_at', 'updated_at', 'actor', 'action_type']
        model = ArgumentActivityAction


class ArgumentActivitySerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    user = MoogtMedaUserSerializer(read_only=True)
    actor = MoogtMedaUserSerializer(read_only=True)
    actions = ArgumentActivityActionSerializer(many=True,  read_only=True)

    class Meta:
        model = ArgumentActivity
        fields = ['id', 'type', 'status', 'created_at', 'actions',
                  'actor', 'actor_id', 'user', 'user_id']
        expandable_fields = dict(
            argument=dict(serializer=ArgumentSerializer, read_only=True),
        )


class ArgumentImageSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['id', 'image']
        model = ArgumentImage


class CommentSerializer(ReadCommentSerializer):
    class Meta:
        model = ReadCommentSerializer.Meta.model
        fields = ReadCommentSerializer.Meta.fields + ('user_id',)

    def get_submit_date(self, obj):
        return obj.submit_date


class ArgumentReactionSerializer(serializers.Serializer):
    pk = serializers.IntegerField()
    object_type = serializers.CharField()
    object = serializers.SerializerMethodField()

    def get_object(self, reaction_obj):
        obj = reaction_obj.get('object')
        if isinstance(obj, Argument):
            return ArgumentSerializer(obj, context={**self.context, 'expand': {'images'}}).data
        elif isinstance(obj, View):
            from views.serializers import ViewSerializer

            return ViewSerializer(obj, context={**self.context, 'expand': {'images'}}).data


class ListArgumentSerialier(serializers.Serializer):
    id = IntegerField()
    type = SerializerMethodField()
    object = SerializerMethodField()
    created = DateTimeField()

    def get_object(self, message_obj):
        obj = message_obj

        from moogts.serializers import MoogtStatusSerializer, MoogtActivityBundleSerializer

        if isinstance(obj, Argument):
            return ArgumentSerializer(obj, context={**self.context}).data
        elif isinstance(obj, MoogtStatus):
            return MoogtStatusSerializer(obj, context={**self.context,
                                                       'expand': {},
                                                       'exclude': {}}).data
        elif isinstance(obj, MoogtActivityBundle):
            return MoogtActivityBundleSerializer(obj, context={**self.context,
                                                               'expand': {},
                                                               'exclude': {}}).data
        return None

    def get_type(self, message_obj):
        obj = message_obj
        if isinstance(obj, Argument):
            return 'argument'
        elif isinstance(obj, MoogtStatus):
            return 'status'
        elif isinstance(obj, MoogtActivityBundle):
            return 'bundle'
        return None


class ArgumentReportSerializer(serializers.ModelSerializer):

    class Meta:
        fields = ['id', 'link', 'reason', 'remark']
        model = ArgumentReport
