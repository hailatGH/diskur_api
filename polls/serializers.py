import datetime

from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ValidationError
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin
from django_comments_xtd.api.frontend import commentbox_props
from django_comments_xtd.models import XtdComment
from django.contrib.contenttypes.models import ContentType
from users.serializers import MoogtMedaSignupSerializer

from users.serializers import MoogtMedaUserSerializer
from .models import Poll, PollReport, PollStats, PollOption


class PollStatSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    share_count = SerializerMethodField()

    class Meta:
        model = PollStats
        fields = ['share_count']

    def get_share_count(self, poll_stats):
        return poll_stats.func_get_share_count()


class PollOptionSerializer(serializers.ModelSerializer):
    win_percentage = SerializerMethodField()
    has_voted = SerializerMethodField()
    num_of_votes = SerializerMethodField()

    class Meta:
        model = PollOption
        fields = ['id', 'content', 'win_percentage',
                  'num_of_votes', 'has_voted']

    def get_win_percentage(self, poll_option):
        return poll_option.win_percentage()

    def get_has_voted(self, poll_option):
        user = self.context['request'].user
        return poll_option.votes.filter(pk=user.pk).exists()

    def get_num_of_votes(self, poll_option):
        if hasattr(poll_option, 'vote_count'):
            return getattr(poll_option, 'vote_count')

    @staticmethod
    def has_user_voted(votes, user):
        return any(vote.id == user.id for vote in votes)


class PollNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    class Meta:
        model = Poll
        fields = ['id', 'title']


class PollSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    options = PollOptionSerializer(many=True)
    total_votes = SerializerMethodField()
    can_vote = SerializerMethodField()
    overall_time_left = SerializerMethodField()
    stats = SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = Poll
        fields = ['id', 'title', 'visibility',
                  'options', 'created_at', 'total_votes', 'can_vote', 'max_duration',
                  'overall_time_left', 'start_date', 'end_date', 'comment_count', 'stats', 'user', 'user_id']

    def create(self, validated_data):
        options = validated_data.pop('options')
        validated_data['user'] = self.context['request'].user
        validated_data['options'] = options
        return Poll.objects.create(**validated_data)

    def validate(self, data):
        if not data.get('max_duration'):
            raise ValidationError('You must provide the duration of the poll.')

        if data.get('max_duration') < datetime.timedelta(minutes=5):
            raise ValidationError(
                'The minimum duration for a poll is 5 minutes.')

        if data.get('max_duration') > datetime.timedelta(days=30):
            raise ValidationError(
                'The minimum duration for a poll is 30 days.')

        return data

    def get_total_votes(self, poll):
        return poll.total_vote

    def get_can_vote(self, poll):
        # This means the poll has expired
        if poll.has_expired():
            return False

        if poll.user == self.context['request'].user:
            return False

        if hasattr(poll, 'can_vote'):
            return getattr(poll, 'can_vote')

        return True

    def get_overall_time_left(self, poll):
        return int(poll.overall_clock_time_remaining().total_seconds())

    def get_stats(self, poll):
        ctype = ContentType.objects.get_for_model(poll)
        return {
            'comment': {**commentbox_props(poll, self.context['request'].user),
                        'selected': XtdComment.objects.filter(user_id=self.context['request'].user.id,
                                                              content_type=ctype,
                                                              object_pk=poll.pk).exists()},
        }

class PollReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PollReport
        fields = ['id', 'link', 'reason', 'remark']