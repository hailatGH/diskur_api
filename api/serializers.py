# Standard library imports

# Third-party and django imports
from avatar.conf import settings as avatar_settings
from avatar.models import Avatar
from avatar.utils import get_default_avatar_url
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.shortcuts import get_current_site
from django_comments_xtd.api.serializers import ReadCommentSerializer, WriteCommentSerializer
from django_comments_xtd.models import XtdComment
from dj_rest_auth.serializers import PasswordResetSerializer
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.fields import SerializerMethodField, CharField
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin
from rest_framework_jwt.compat import Serializer
from rest_framework_jwt.serializers import jwt_payload_handler, jwt_encode_handler
from django.utils.translation import gettext as _


# Local Django imports from other apps
from moogts.models import Moogt
from users.models import Activity, MoogtMedaUser, PhoneNumber
from users.serializers import MoogtMedaUserSerializer
from users.utils import verify_firebase_user
from .mixins import TrendingMixin
from .models import (Tag)


class TagSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    name = CharField(max_length=200)

    class Meta:
        model = Tag
        fields = ['name']


class AvatarSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    resized_avatar = SerializerMethodField()

    class Meta:
        model = Avatar
        fields = ['id', 'avatar', 'primary', 'resized_avatar']

    def get_resized_avatar(self, avatar):
        if avatar:
            size = self.context['view'].kwargs.get('size')
            if not size:
                size = avatar_settings.AVATAR_DEFAULT_SIZE
            return avatar.avatar_url(int(size))

        return get_default_avatar_url()


class SidebarSerializer(serializers.Serializer):
    moogt_count = serializers.SerializerMethodField()
    subscriber_count = serializers.SerializerMethodField()
    subscribed_count = serializers.SerializerMethodField()
    open_invitation_count = serializers.SerializerMethodField()
    wallet_amount = serializers.SerializerMethodField()
    donations_amount = serializers.SerializerMethodField()

    class Meta(object):
        fields = ['moogt_count', 'subscriber_count', 'subscribed_count',
                  'open_invitation_count', 'wallet_amount', 'donations_amount']

    def get_moogt_count(self, obj):
        return obj.get('moogt_count')

    def get_subscriber_count(self, obj):
        return obj.get('subscriber_count')

    def get_subscribed_count(self, obj):
        return obj.get('subscribed_count')

    def get_open_invitation_count(self, obj):
        return obj.get('open_invitation_count')

    def get_wallet_amount(self, obj):
        return obj.get('wallet_amount')

    def get_donations_amount(self, obj):
        return obj.get('donations_amount')


class ActivitySerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta(object):
        model = Activity
        fields = ['id', 'type', 'created_at', 'object_id', 'user']

    def get_user(self, obj):
        return MoogtMedaUserSerializer(MoogtMedaUser.objects.get(pk=obj.profile.user.pk),
                                       context={'request': self.context['request']}).data


class UserProfileSerializer(SerializerExtensionsMixin, TrendingMixin, serializers.Serializer):
    items = serializers.SerializerMethodField()
    is_self_profile = serializers.SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)
    views_count = serializers.SerializerMethodField()
    moogts_count = serializers.SerializerMethodField()
    polls_count = serializers.SerializerMethodField()
    live_moogts_count = serializers.SerializerMethodField()
    premiering_moogts_count = serializers.SerializerMethodField()

    class Meta(object):
        fields = ["items", "activities",
                  "moogts_count", 'views_count', 'polls_count',
                  "is_self_profile", "user"]

    def get_items(self, data):
        return data['items']

    def get_moogts_count(self, data):
        return data['moogts_count']

    def get_views_count(self, data):
        return data['views_count']

    def get_polls_count(self, data):
        return data['polls_count']

    def get_live_moogts_count(self, data):
        return data['live_moogts_count']

    def get_premiering_moogts_count(self, data):
        return data['premiering_moogts_count']

    def get_activities(self, data):
        if self.context['request'].user.is_authenticated:
            try:
                user = MoogtMedaUser.objects.get(pk=data['user_id'])
                activities = Activity.objects.filter(
                    profile=user.profile).order_by("-created_at")[:5]
                return ActivitySerializer(activities,
                                          context=self.context,
                                          many=True).data

            except MoogtMedaUser.DoesNotExist:
                raise NotFound("User doesn't exist")
        else:
            return []

    def get_follower_count(self, data):
        try:
            return MoogtMedaUser.objects.get(pk=data['user_id']).followers.count()

        except MoogtMedaUser.DoesNotExist:
            raise NotFound("User doesn't exist")

    def get_moogt_created_count(self, data):
        return Moogt.objects.filter(proposition=data['user_id']).count()

    def get_is_self_profile(self, data):
        if self.context['request'].user.pk == None:
            return False
        return self.context['request'].user.pk == data['user'].id


class CreateCommentSerializer(WriteCommentSerializer):
    thread_id = serializers.IntegerField(default=0)

    def save(self):
        resp = super().save()
        comment = resp['comment'].xtd_comment
        comment.thread_id = self.data.get('thread_id')
        comment.save()
        return resp


class CommentNotificationSerializer(ReadCommentSerializer):
    content_type = serializers.SerializerMethodField()

    class Meta:
        model = XtdComment
        fields = ['id', 'comment', 'user_id', 'content_type', 'object_pk']

    def get_content_type(self, obj):
        return obj.content_type.model


class CommentSerializer(ReadCommentSerializer):
    user = MoogtMedaUserSerializer()
    created_at = serializers.SerializerMethodField()

    class Meta(ReadCommentSerializer.Meta):
        fields = ReadCommentSerializer.Meta.fields + \
            ('user', 'created_at', 'user_id', 'thread_id')
        

    def get_flags(self, obj):
        flags = super().get_flags(obj)
        flags['like']['count'] = len(
            flags['like']['users']) if flags['like']['users'] else 0
        flags['reply'] = {
            'count': self.get_replies_count(obj, self.context['request'])
        }
        return flags

    @staticmethod
    def get_replies_count(obj, request):
        content_type = ContentType.objects.get_for_model(obj)

        return XtdComment.objects.filter(
            content_type=content_type,
            object_pk=obj.pk,
            site__pk=get_current_site(request).pk,
            is_public=True
        ).count()

    def get_created_at(self, obj):
        return obj.submit_date


class StatsItemSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    selected = serializers.BooleanField()
    allowed = serializers.BooleanField()


class ReactionStatsSerializer(StatsItemSerializer):
    percentage = serializers.IntegerField(required=False)
    has_reaction_with_statement = serializers.BooleanField()


class BaseViewArgumentSerializer(serializers.Serializer):
    def get_users(self, users):
        return set(users)

    @staticmethod
    def has_user_reacted(user, reactions):
        return any(reaction.user and reaction.user.id == user.id for reaction in reactions)

    @staticmethod
    def has_reaction_without_statement(user, reactions):
        return any(reaction.content is None and reaction.user.id == user.id for reaction in reactions)

    @staticmethod
    def has_reaction_with_statement(user, reactions):
        return any(reaction.content is not None and reaction.user.id == user.id for reaction in reactions)

    def reaction_allowed(self, user, reactions, opposing_reactions):
        if self.has_reaction_with_statement(user, reactions) or self.has_reaction_with_statement(user,
                                                                                                 opposing_reactions):
            return False

        return True

    @staticmethod
    def has_user_applauded(user, applauds):
        return any(user.id == u.id for u in applauds)

    @staticmethod
    def calculate_percentage(count, total):
        if total > 0:
            return round(count * 100 / total)
        else:
            return 50


class CustomPasswordResetSerializer(PasswordResetSerializer):
    def get_email_options(self):
        return {
            'email_template_name': 'meda/password_reset.txt',
            'domain_override': settings.DOMAIN_NAME
        }


class TelegramChatToUserSerializer(serializers.Serializer):
    class Meta(object):
        fields = ["id", "user", "chat_id"]

class FirebaseJSONWebTokenSerializer(Serializer):
    firebase_token = serializers.CharField()
    
    def validate(self, attrs):
        firebase_token = attrs.get('firebase_token')
        
        decoded_token = verify_firebase_user(firebase_token)
        if decoded_token:
            try:
                phone_number = PhoneNumber.objects.get(firebase_uid=decoded_token['uid'])
                user = phone_number.user
                
                if not user.is_active:
                    msg = _('User account is disabled.')
                    raise serializers.ValidationError(msg)
                
                payload = jwt_payload_handler(user)

                return {
                    'token': jwt_encode_handler(payload),
                    'user': user
                }
            except PhoneNumber.DoesNotExist:
                msg = _('You must create an account with your phone number first.')
                raise serializers.ValidationError(msg)
        else:
            msg = _('Something went wrong verifying firebase user.')
            raise serializers.ValidationError(msg)