from django.db.models import Sum, IntegerField
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin

from api.serializers import TagSerializer
from arguments.serializers import ArgumentSerializer
from invitations.serializers import InvitationSerializer
from meda.enums import InvitationStatus
from moogts.models import MoogtActivityAction
from moogts.models import Moogt, MoogtMiniSuggestion, MoogtBanner, MoogtActivity, Donation, MoogtReport, MoogtStatus, \
    MoogtActivityBundle
from users.serializers import MoogtMedaUserSerializer


class MoogtBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = MoogtBanner
        fields = ('id', 'banner')

    def validate_banner(self, banner):
        # Max file size is 2 mb.
        max_file_size = 2 * 1024 * 1024
        if banner.size > max_file_size:
            raise ValidationError('File size is bigger than 2MB.')
        min_width = 630
        min_height = 210
        width, height = banner.image.size
        if width < min_width or height < min_height:
            raise ValidationError('Image resolution too small.')

        aspect_ratio = width / height
        if 3.1 < aspect_ratio < 2.9:
            raise ValidationError('Image Aspect Ratio should be 3:1.')

        return banner


class MoogtNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):

    class Meta:
        model = Moogt
        fields = ['id', 'resolution', 'proposition', 'opposition', 'banner']


class MoogtSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    moogt_clock_seconds = serializers.SerializerMethodField()
    idle_timer_expire_seconds = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_moogt_participant = serializers.SerializerMethodField()
    moogt_duration_seconds = serializers.SerializerMethodField()
    idle_timeout_duration_seconds = serializers.SerializerMethodField()
    share_count = serializers.SerializerMethodField()
    total_donations = serializers.SerializerMethodField()
    your_donations = serializers.SerializerMethodField()
    is_current_turn = serializers.SerializerMethodField()
    next_turn_user_id = serializers.SerializerMethodField()
    arguments_count = serializers.SerializerMethodField()
    unread_cards_count = serializers.SerializerMethodField()
    latest_read_at = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    is_premiering_moogt = serializers.SerializerMethodField()
    moderator = MoogtMedaUserSerializer(read_only=True)
    opposition = MoogtMedaUserSerializer(read_only=True)
    proposition = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = Moogt
        fields = ['id', 'numberOfCard', 'resolution', 'created_at', 'updated_at', 'started_at',
                  'moogt_clock_seconds', 'idle_timer_expire_seconds', 'max_duration', 'idle_timeout_duration',
                  'description', 'moogt_duration_seconds', 'idle_timeout_duration_seconds',
                  'premiering_date', 'tags', 'visibility', 'stats',
                  'type', 'followers_count', 'is_following', 'is_moogt_participant',
                  'total_donations', 'your_donations', 'arguments_count', 'latest_read_at',
                  'next_turn_proposition', 'share_count', 'has_ended', 'unread_cards_count',
                  'moderator', 'moderator_id', 'opposition', 'opposition_id', 'proposition', 'proposition_id', 'is_current_turn', 'next_turn_user_id', 'is_paused', 'is_premiering_moogt']
        expandable_fields = dict(
            tags=dict(serializer=TagSerializer, many=True, required=False),
            arguments=dict(serializer=ArgumentSerializer,
                           many=True, read_only=True),
            quit_by=dict(serializer=MoogtMedaUserSerializer, read_only=True),
            banner=dict(serializer=MoogtBannerSerializer, read_only=True),
            activities=dict(
                serializer='moogts.serializers.MoogtActivitySerializer', many=True)
        )

    def create(self, validated_data):
        return Moogt.objects.create(**validated_data)

    def update(self, instance, validated_data):
        clone = validated_data.pop(
            'clone') if 'clone' in validated_data else False
        banner = validated_data.pop(
            'banner') if 'banner' in validated_data else False
        if clone:
            instance.pk = None

        if banner:
            instance.banner_id = banner

        instance.save()
        return super().update(instance, validated_data)

    def get_render_moogt_clock(self, moogt):
        return moogt.func_has_started() and not moogt.func_has_ended_or_expired()

    def get_moogt_clock_seconds(self, moogt: Moogt):
        if self.get_is_premiering_moogt(moogt):
            return (moogt.premiering_date - timezone.now()).total_seconds()
        elif self.get_render_moogt_clock(moogt):
            if moogt.func_overall_clock_time_remaining():
                return moogt.func_overall_clock_time_remaining().total_seconds()

    def get_render_invitation_card(self, moogt):
        try:
            user = self.context['request'].user
            if not user.is_authenticated:
                return False

            for invitation in moogt.invitations.all():
                if invitation.invitee == user and invitation.status == InvitationStatus.pending():
                    return True
            return False
        except KeyError:
            return None

    def get_open_invitation(self, moogt):
        try:
            user = self.context['request'].user
            for invitation in moogt.invitations.all():
                '''
                reason made for invitee and inviter only is because we want invitee for render_invitation_card
                and inviter for render_waiting card
                '''
                if (
                        invitation.invitee == user or invitation.inviter == user) and invitation.status == InvitationStatus.pending():
                    invitation_serializer = InvitationSerializer(invitation, context={**self.context,
                                                                                      'expand': ['inviter', 'invitee'],
                                                                                      'exclude': ['moogt']})
                    return invitation_serializer.data
            return None
        except KeyError:
            return None

    def get_render_invite_button(self, moogt):
        try:
            user = self.context['request'].user
            if (not user.is_authenticated) or (user != moogt.proposition) or (moogt.opposition is not None):
                return False

            for invitation in moogt.invitations.all():
                if invitation.status == InvitationStatus.pending() or invitation.status == InvitationStatus.accepted():
                    return False
            return True
        except KeyError:
            return None

    def get_latest_read_at(self, moogt):
        if self.context['request'].user.is_authenticated:
            latest_read_by = self.context['request'].user.read_moogts.filter(
                moogt=moogt).first()
            if latest_read_by:
                return latest_read_by.latest_read_at

    def get_render_waiting_card(self, moogt):
        try:
            user = self.context['request'].user
            if not user.is_authenticated or user != moogt.proposition:
                return False

            for invitation in moogt.invitations.all():
                if invitation.inviter == user and invitation.status == InvitationStatus.pending():
                    return True

            return False
        except KeyError:
            return None

    def get_render_accept_form(self, moogt):
        try:
            user = self.context['request'].user
            if not user.is_authenticated:
                return False

            for invitation in moogt.invitations.all():
                if (invitation.status == InvitationStatus.pending() or
                        invitation.status == InvitationStatus.accepted()):
                    return False

            if moogt.opposition is None:
                return user != moogt.proposition

            return False
        except KeyError:
            return None

    def get_render_idle_timer(self, moogt):
        if not moogt.func_has_started() or moogt.func_has_ended_or_expired():
            return False
        return True

    def get_idle_timer_expire_seconds(self, moogt):
        if moogt.func_idle_timer_expire_time_remaining() is not None:
            return moogt.func_idle_timer_expire_time_remaining().total_seconds()

    def get_render_argument_form(self, moogt):
        try:
            user = self.context['request'].user
            if moogt.func_has_ended_or_expired():
                return False

            if not user.is_authenticated:
                return False

            if moogt.get_next_turn_proposition():
                return user == moogt.get_proposition()
            else:
                return user == moogt.get_opposition()
        except KeyError:
            return None

    def get_moogt_duration_seconds(self, moogt):
        if moogt.get_max_duration():
            return moogt.max_duration.total_seconds()

    def get_idle_timeout_duration_seconds(self, moogt):
        return moogt.get_idle_timeout_duration().total_seconds()

    def get_followers_count(self, moogt):
        return moogt.followers.count()

    def get_is_following(self, moogt):
        request = self.context.get('request')
        if not request:
            return False

        return request.user in moogt.followers.all()

    def get_is_moogt_participant(self, moogt):
        request = self.context.get('request')
        if not request:
            return False
        if request.user == moogt.get_moderator():
            return True
        return request.user == moogt.get_proposition() or request.user == moogt.get_opposition()

    def get_render_last_word_card(self, moogt):
        if moogt.get_end_requested_by_proposition():
            if self.context['request'].user == moogt.get_opposition() and moogt.get_next_turn_proposition():
                return True
        else:
            if self.context['request'].user == moogt.get_proposition() and moogt.get_next_turn_proposition() is False:
                return True

        return False

    def get_total_donations(self, moogt):
        return moogt.donations.aggregate(Sum('amount', output_field=IntegerField()))['amount__sum']

    def get_your_donations(self, moogt):
        qs = moogt.donations
        if self.context['request'].user == moogt.opposition:
            qs = qs.filter(donation_for_proposition=False)
        elif self.context['request'].user == moogt.proposition:
            qs = qs.filter(donation_for_proposition=True)

        return qs.aggregate(Sum('amount', output_field=IntegerField()))['amount__sum']

    def get_unread_cards_count(self, moogt):
        if self.context['request'].user.is_authenticated:
            return moogt.unread_cards_count(self.context['request'].user)

    def get_share_count(self, moogt):
        return moogt.stats.func_get_share_count()

    def get_is_current_turn(self, moogt):
        user = self.context['request'].user
        return moogt.func_is_current_turn(user)

    def get_is_premiering_moogt(self, moogt):
        return moogt.is_premiering
        # and moogt.premiering_date > timezone.now()

    def get_next_turn_user_id(self, moogt):
        if moogt.get_next_turn_proposition():
            return moogt.get_proposition().pk

        if moogt.get_opposition():
            return moogt.get_opposition().pk

    def get_arguments_count(self, moogt):
        return getattr(moogt, 'arguments_count', 0)

    def get_stats(self, moogt):
        return {
            'proposition_endorsement_count': moogt.proposition_endorsement,
            'proposition_disagreement_count': moogt.proposition_disagreement,
            'opposition_endorsement_count': moogt.opposition_endorsement,
            'opposition_disagreement_count': moogt.opposition_disagreement
        }


class MoogtMiniSuggestionNotificationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    moogt = serializers.StringRelatedField()

    class Meta:
        model = MoogtMiniSuggestion
        fields = ['id', 'moogt']


class MoogtMiniSuggestionSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    allowed_fields = ['moderator', 'resolution', 'description', 'max_duration', 'banner', 'remove_banner',
                      'idle_timeout_duration', 'visibility', 'tags', 'premiering_date', 'stop_countdown']

    max_duration_seconds = serializers.SerializerMethodField()
    idle_timeout_duration_seconds = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    edited_parent_id = serializers.SerializerMethodField()
    suggested_child_id = serializers.SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)
    moderator = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = MoogtMiniSuggestion
        fields = ['id', 'state', 'edited_parent_id', 'suggested_child_id',
                  'resolution', 'description', 'max_duration', 'premiering_date', 'remove_banner',
                  'max_duration_seconds', 'idle_timeout_duration_seconds', 'stop_countdown',
                  'idle_timeout_duration', 'visibility', 'type', 'user', 'user_id', 'moderator', 'moderator_id']
        expandable_fields = dict(
            moogt=dict(serializer=MoogtSerializer, read_only=True),
            tags=dict(serializer=TagSerializer, many=True),
            banner=dict(serializer=MoogtBannerSerializer, read_only=True)
        )

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user

        tags = validated_data.pop('tags') if 'tags' in validated_data else []
        mini_suggestion = MoogtMiniSuggestion.objects.create(**validated_data)
        if tags:
            mini_suggestion.add_tags(tags)
        return mini_suggestion

    @staticmethod
    def is_suggestion_valid(data):

        valid = False

        for field in MoogtMiniSuggestionSerializer.allowed_fields:
            if data.get(field, None) is not None and valid is False:
                valid = True
            elif data.get(field, None) is not None:
                raise ValidationError('More than one field has been set')

        return valid

    def get_type(self, suggestion):
        return suggestion.get_type()

    def get_max_duration_seconds(self, suggestion):
        if suggestion.max_duration:
            return suggestion.max_duration.total_seconds()

    def get_idle_timeout_duration_seconds(self, suggestion):
        if suggestion.idle_timeout_duration:
            return suggestion.idle_timeout_duration.total_seconds()

    def get_edited_parent_id(self, suggestion):
        if getattr(suggestion, 'edited_parent', False):
            return suggestion.edited_parent.id

    def get_suggested_child_id(self, suggestion):
        if getattr(suggestion, 'suggested_child', False):
            return suggestion.suggested_child.id


class MoogtActivityBundleSerializer(SerializerExtensionsMixin,
                                    serializers.ModelSerializer):
    class Meta:
        model = MoogtActivityBundle
        fields = ['id']
        expandable_fields = dict(
            moogt=dict(serializer=MoogtSerializer, read_only=True)
        )


class MoogtActivityActionSerializer(serializers.ModelSerializer):
    actor = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = MoogtActivityAction
        fields = ['id', 'created_at', 'updated_at', 'actor', 'action_type']


class MoogtActivitySerializer(SerializerExtensionsMixin,
                              serializers.ModelSerializer):

    user = MoogtMedaUserSerializer(read_only=True)
    actor = MoogtMedaUserSerializer(read_only=True)
    actions = MoogtActivityActionSerializer(many=True, read_only=True)

    class Meta:
        model = MoogtActivity
        fields = ('id', 'type', 'status', 'created_at', 'updated_at',
                  'user', 'user_id', 'actor', 'actor_id', 'actions')
        expandable_fields = dict(
            moogt=dict(serializer=MoogtSerializer, read_only=True),
            bundle=dict(serializer=MoogtActivityBundleSerializer,
                        read_only=True),
            react_to=dict(serializer=ArgumentSerializer, read_only=True)

        )

    def create(self, validated_data):
        validated_data['moogt'] = self.context['request'].data.get('moogt')
        validated_data['user'] = self.context['request'].user
        validated_data['actor'] = self.context['request'].data.get('actor')
        return super().create(validated_data)


class MoogtActivityBundleSerializer(SerializerExtensionsMixin,
                                    serializers.ModelSerializer):
    activities_count = serializers.SerializerMethodField()

    class Meta:
        model = MoogtActivityBundle
        fields = ['id', 'activities_count']
        expandable_fields = dict(
            moogt=dict(serializer=MoogtSerializer, read_only=True)
        )

    def get_activities_count(self, bundle):
        return bundle.activities_count


class MoogtStatusSerializer(SerializerExtensionsMixin,
                            serializers.ModelSerializer):

    user = MoogtMedaUserSerializer(read_only=True)

    class Meta:
        model = MoogtStatus
        fields = ['id', 'status', 'created_at', 'updated_at',
                  'user', 'user_id']

        expandable_fields = dict(
            moogt=dict(serializer=MoogtSerializer, read_only=True),
        )


class MoogtHighlightsSerializer(SerializerExtensionsMixin, serializers.Serializer):
    applauded = serializers.SerializerMethodField()
    most_agreed = ArgumentSerializer()
    most_disagreed = ArgumentSerializer()
    most_commented = ArgumentSerializer()

    class Meta:
        fields = ['most_applauded', 'most_agreed',
                  'most_disagreed', 'most_commented']


class DonationSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):

    user = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()

    class Meta:
        model = Donation
        fields = ['id', 'donation_for_proposition', 'level', 'amount',
                  'created_at', 'message', 'user_id', 'is_anonymous', 'user']
        extra_kwargs = {
            'donation_for_proposition': {'required': True},
        }
        expandable_fields = dict(
            moogt=dict(serializer=MoogtSerializer, read_only=True),
            donated_for=dict(
                serializer=MoogtMedaUserSerializer, read_only=True),
        )

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        validated_data['donated_for_id'] = self.context['request'].data.get(
            'donated_for', None)
        return super().create(validated_data)

    def get_user_id(self, donation: Donation):
        if not donation.is_anonymous:
            return donation.user.id

    def get_user(self, donation: Donation):
        if not donation.is_anonymous:
            return MoogtMedaUserSerializer(donation.user).data


class MoogtReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MoogtReport
        fields = ['id', 'link', 'reason', 'remark']
