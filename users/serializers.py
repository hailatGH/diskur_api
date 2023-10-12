from avatar.conf import settings as avatar_settings
from avatar.utils import get_primary_avatar
from django.conf import settings as django_settings
from dj_rest_auth.registration.serializers import RegisterSerializer
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework_serializer_extensions.serializers import SerializerExtensionsMixin
from rest_framework.exceptions import ValidationError
from api.mixins import TrendingMixin
from moogts.models import Moogt
from .utils import verify_firebase_user
from .models import AccountReport, MoogtMedaUser, Profile, Activity, Wallet


class MoogtMedaSignupSerializer(RegisterSerializer):
    
    first_name = serializers.CharField(required=True, write_only=True)

    def update(self, instance, validated_data):
        pass

    def create(self, validated_data):
        pass

    def custom_signup(self, request, user):
        user.first_name = self.validated_data.get('first_name', '')
        user.save(update_fields=['first_name', ])

    def save(self, request):
        # self.custom_validation(self.validated_data)
        user = super(MoogtMedaSignupSerializer, self).save(request)

        # Create an associated new profile for the user.
        new_profile = Profile()
        new_profile.user = user
        new_profile.save()

        # Create associated wallet for the user.
        Wallet.objects.create(user=user)

        return user


class ProfileModelSerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    class Meta(object):
        model = Profile
        fields = ['bio', 'cover_photo', 'quote', 'profile_photo']

    def validate(self, attrs):
        profile_photo = attrs.get('profile_photo', None)
        cover_photo = attrs.get('cover_photo', None)
        if profile_photo:
            width = profile_photo.image.width
            height = profile_photo.image.height
            size = profile_photo.size
            megabyte_limit = 2.0
            if width != height:
                raise ValidationError(
                    'The width and height of your image must be the same'
                )
            if size > megabyte_limit*1024*1024:
                raise ValidationError(
                    'The maximum file size must be less than 2MB'
                )

        if cover_photo:
            width = cover_photo.image.width
            height = cover_photo.image.height
            size = cover_photo.size
            megabyte_limit = 4.0
            aspect_ratio = width/height

            if aspect_ratio > 3.05 or aspect_ratio <= 2.95:
                raise ValidationError(
                    'the ratio must be 3:1'
                )
            if size > megabyte_limit*1024*1024:
                raise ValidationError(
                    'The maximum file size must be less than 4MB'
                )

        return attrs


class MoogtMedaUserSerializer(SerializerExtensionsMixin,
                              serializers.ModelSerializer):
    can_follow = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_blocking = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    profile = ProfileModelSerializer()

    class Meta:
        model = MoogtMedaUser
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'can_follow',
                  'followers_count', 'is_following', 'bio', 'quote', 'cover', 'is_blocking',
                  'profile', 'is_blocked', 'avatar_url', 'date_joined']

    def update(self, instance, validated_data):

        profile_data = validated_data.pop('profile', None)
        instance = super().update(instance, validated_data)

        if profile_data is not None:
            profile_serializer = ProfileModelSerializer(data=profile_data)

            if profile_serializer.is_valid():
                profile_serializer.update(
                    instance=instance.profile, validated_data=profile_serializer.validated_data)

        return instance

    def get_can_follow(self, user):
        if 'request' not in self.context:
            return None

        return user.can_follow(self.context['request'].user)

    def get_followers_count(self, user):
        return getattr(user, 'followers_count', 0)

    def get_is_following(self, user):
        return getattr(user, 'is_following', False)

    def get_avatar_url(self, user):
        if user.profile and user.profile.profile_photo:
            if django_settings.DEBUG and self.context.get('request', None):
                return self.context['request'].build_absolute_uri(user.profile.profile_photo.url)
            
            return user.profile.profile_photo.url
        
        return None

    def get_is_blocking(self, user):
        return getattr(user, 'is_blocking', False)

    def get_is_blocked(self, user):
        return getattr(user, 'is_blocked', False)


class UserProfileSerializer(SerializerExtensionsMixin, TrendingMixin, serializers.Serializer):
    items = serializers.SerializerMethodField()
    is_self_profile = serializers.SerializerMethodField()
    user = MoogtMedaUserSerializer(read_only=True)

    class Meta(object):
        fields = ["items", "activities", "is_self_profile", "user"]

    def get_items(self, data):
        return data['items']

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
        if self.context['request'].user.pk is None:
            return False
        return self.context['request'].user.pk == data['user'].id


class ActivitySerializer(SerializerExtensionsMixin, serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta(object):
        model = Activity
        fields = ['id', 'type', 'created_at', 'object_id', 'user']

    def get_user(self, obj):
        return MoogtMedaUserSerializer(MoogtMedaUser.objects.get(pk=obj.profile.user.pk),
                                       context={'request': self.context['request']}).data


class RefillWalletSerializer(serializers.Serializer):
    level1 = serializers.IntegerField(min_value=1, required=False)
    level2 = serializers.IntegerField(min_value=1, required=False)
    level3 = serializers.IntegerField(min_value=1, required=False)
    level4 = serializers.IntegerField(min_value=1, required=False)
    level5 = serializers.IntegerField(min_value=1, required=False)

    def get_amount(self):
        level1 = self.validated_data.get('level1', 0)
        level2 = self.validated_data.get('level2', 0)
        level3 = self.validated_data.get('level3', 0)
        level4 = self.validated_data.get('level4', 0)
        level5 = self.validated_data.get('level5', 0)

        amount = 0
        if level1 > 0:
            amount += 100 * level1

        if level2 > 0:
            amount += 1_000 * level2

        if level3 > 0:
            amount += 10_000 * level3

        if level4 > 0:
            amount += 100_000 * level4

        if level5 > 0:
            amount += 1_000_000 * level5

        return amount

    def validate(self, data):
        """
        Check if at least one level is present in data.
        """
        if data.get('level1') or data.get('level2') or data.get('level3') or data.get('level4') or data.get('level5'):
            return data

        raise serializers.ValidationError('You must choose at least one level')
    
class AccountReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountReport
        fields = ['id', 'link', 'reason', 'remark']
        

class PhoneNumberSignupSerializer(MoogtMedaSignupSerializer):
    phone_number = serializers.CharField()
    
    firebase_token = serializers.CharField()
    
    email = serializers.EmailField(required=False)
    
    password1 = serializers.CharField(required=False)
    
    password2 = serializers.CharField(required=False)
    
    def validate(self, data):

        return data