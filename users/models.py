from enum import Enum
from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image

from annoying.fields import AutoOneToOneField
from django.apps import apps
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage as storage
from django.db.models import Count
from django.forms import ValidationError
from django.shortcuts import reverse, get_object_or_404
from django_comments.signals import comment_was_posted
from model_utils import Choices

from meda.behaviors import Timestampable
from meda.models import BaseReport
from users.managers import MoogtMedaUserManager


# A simple function for rendering a user in the @username format.
def moogtmeda_user_display(user):
    return "@%s" % user.username


class MoogtMedaUser(AbstractUser):
    """A custom user class for MoogtMeda."""
    objects = MoogtMedaUserManager()

    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
        max_length=15,
        unique=True,
        help_text='Required. 15 characters or fewer. Letters, digits and @/./+/-/_ only.',
        validators=[username_validator],
        error_messages={
            'unique': "A user with that username already exists.",
        },
    )

    first_name = models.CharField(max_length=50, blank=True)

    """
    TODO Delete these 3 fields(quote, bio and cover). We’re currently
    keeping them because we may have to touch every connection made on these 3 fields
    """

    quote = models.CharField(max_length=200, null=True)

    bio = models.CharField(max_length=200, null=True)

    cover = models.ImageField(blank=True)

    follower = models.ManyToManyField('self',
                                      related_name="followings",
                                      symmetrical=False)

    following = models.ManyToManyField('self',
                                       related_name="followers",
                                       symmetrical=False)

    following_moogts = models.ManyToManyField("moogts.Moogt",
                                              related_name='followers')

    last_opened_moogt = models.ForeignKey("moogts.Moogt",
                                          on_delete=models.SET_NULL,
                                          null=True,
                                          related_name='+')

    last_opened_following_moogt = models.ForeignKey("moogts.Moogt",
                                                    on_delete=models.SET_NULL,
                                                    null=True,
                                                    related_name='+')

    priority_conversations = models.ManyToManyField("chat.conversation",
                                                    related_name='prioritizers')

    def __str__(self):
        if self.first_name:
            if len(self.first_name) > 15:
                return f'{self.first_name[:15]}...'
            return self.first_name

        return self.get_username()

    def can_follow(self, followee):
        """
        Make sure you are not following yourself.
        """
        return self.pk != followee.pk


class Profile(models.Model):
    """A model for managing a user's profile."""

    user = AutoOneToOneField(MoogtMedaUser,
                             on_delete=models.CASCADE,
                             related_name='profile',
                             primary_key=True)

    quote = models.CharField(max_length=200, null=True)

    bio = models.CharField(max_length=200, null=True)

    cover_photo = models.ImageField(upload_to='cover_photos', blank=True)

    profile_photo = models.ImageField(upload_to='profile_photos', blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.profile_photo:
            original_image = storage.open(self.profile_photo.name, 'rb')
            img = Image.open(original_image)

            if img.height > 500 or img.width > 500:
                new_img = (500, 500)
                img.thumbnail(new_img)

                imageBuffer = BytesIO()
                img.save(imageBuffer, img.format)
                self.profile_photo.save(
                    self.profile_photo.name, ContentFile(imageBuffer.getvalue()))

            original_image.close()

        if self.cover_photo:
            original_image = storage.open(self.cover_photo.name, 'rb')
            img = Image.open(original_image)

            if img.width > 600 or img.height > 200:
                new_img = (600, 200)
                img.thumbnail(new_img)

                imageBuffer = BytesIO()
                img.save(imageBuffer, img.format)
                self.cover_photo.save(
                    self.cover_photo.name, ContentFile(imageBuffer.getvalue()))

            original_image.close()

    def credit_pts(self):
        return sum([credit_point.val() for credit_point in self.credit_points.all()])

    def activity_pts(self):
        return sum([activity.xp() for activity in self.activities.all()])

    def credit_pts_count(self):
        return self.credit_points.values('type').annotate(Count('type'))

    def xp(self):
        return self.activity_pts() + self.credit_pts()

    def __str__(self):
        return "Profile for user: " + str(self.user)


class Wallet(Timestampable):
    """A wallet for users. This is used for making donations."""
    LEVEL = Choices('level_1', 'level_2', 'level_3', 'level_4', 'level_5')

    user = AutoOneToOneField(MoogtMedaUser,
                             related_name='wallet',
                             on_delete=models.CASCADE,
                             primary_key=True)

    credit = models.DecimalField(
        max_digits=10, decimal_places=2, default=5_000)


class ActivityType(Enum):
    """Represents a kind of activity a user can do."""
    create_moogt = "Create Moogt"
    create_argument = "Create Argument"
    follow_user = "Follow User"
    unfollow_user = "Unfollow user"
    view_moogt = "View Moogt"
    follow_moogt = "Follow Moogt"
    view_proposition_moogt = "View Proposition Moogt"
    view_opposition_moogt = "View Opposition Moogt"
    make_comment = "Make Comment"
    upvote_argument = "Upvote Argument"
    downvote_argument = "Downvote Argument"


class Activity(models.Model):
    """A base class for any noteworthy activity by on MoogtMeda."""

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="activities")
    created_at = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=25, choices=[(
        type.name, type.value) for type in ActivityType])
    object_id = models.IntegerField(null=True, default=None)

    def href(self):
        if self.object_id is None:
            return None

        if self.type == ActivityType.create_moogt.name or self.type == ActivityType.view_moogt.name:
            return reverse("meda:detail", args=[self.object_id])
        elif self.type == ActivityType.create_argument.name or self.type == ActivityType.make_comment.name:
            argument_model = apps.get_model('meda', 'Argument')
            argument = get_object_or_404(argument_model, id=self.object_id)
            moogt = argument.moogt
            return "%s#%s" % (reverse("meda:detail", args=[moogt.id]), argument.id)
        elif self.type == ActivityType.follow_user.name:
            user = get_object_or_404(MoogtMedaUser, id=self.object_id)
            return reverse("users:anonymous_profile", args=[user.username])

    def xp(self):
        if self.type == ActivityType.create_moogt.name:
            return 10
        if self.type == ActivityType.create_argument.name:
            return 20
        if self.type == ActivityType.follow_user.name:
            return 30
        else:
            return 0

    def description(self):
        if self.type == ActivityType.create_moogt.name:
            return "You created a moogt."
        if self.type == ActivityType.create_argument.name:
            return "You made an argument."
        if self.type == ActivityType.follow_user.name:
            return "You followed a user."
        if self.type == ActivityType.view_moogt.name:
            return "You viewed a moogt."
        if self.type == ActivityType.make_comment.name:
            return "You made a comment."
        if self.type == ActivityType.upvote_argument.name:
            return "You upvoted an argument."
        if self.type == ActivityType.downvote_argument.name:
            return "You downvoted an argument."
        else:
            return "You did something."

    @staticmethod
    def record_activity(profile, activity_type, object_id):
        activity = Activity()
        activity.profile = profile
        activity.type = activity_type
        activity.object_id = object_id
        activity.save()

        return activity

    @staticmethod
    def new_comment_recorder(sender, comment, request, *args, **kwargs):
        activity = Activity.record_activity(
            request.user.profile, ActivityType.make_comment.name, comment.id)
        CreditPoint.create(
            activity, ActivityType.make_comment.name, request.user.profile)


class CreditPoint(models.Model):
    activity = models.ForeignKey(
        Activity, related_name='credit_points', on_delete=models.SET_NULL, null=True)
    type = models.CharField(max_length=25, choices=[(
        type.name, type.value) for type in ActivityType], default='')
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='credit_points', null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def create(activity, activity_type_name, profile):
        credit_point = CreditPoint(
            activity=activity, type=activity_type_name, profile=profile)
        credit_point.save()

        return credit_point

    def val(self):
        if self.type == ActivityType.view_opposition_moogt.name or \
                self.type == ActivityType.view_proposition_moogt.name:
            return 40
        if self.type == ActivityType.make_comment.name:
            return 50
        if self.type == ActivityType.upvote_argument.name:
            return 60
        if self.type == ActivityType.downvote_argument.name:
            return 70

    @staticmethod
    def create_upvote_downvote_credit_point(activity_type, activity, argument):

        credit_point = CreditPoint.objects.filter(
            profile=argument.user.profile, activity__object_id=argument.id)
        credit_point = credit_point.filter(type=ActivityType.upvote_argument.name) | credit_point.filter(
            type=ActivityType.downvote_argument.name)

        if not credit_point.exists():
            CreditPoint.create(activity, activity_type.name,
                               argument.user.profile)
        else:
            credit_point.update(type=activity_type.name)


class Blocking(Timestampable):
    """A model used to represent the concept of user blocking another user.

    Attributes
    ----------
    user : ForeignKey
        The user who is doing the blocking, i.e., `blocked_user`.

    blocked_user : ForeignKey
        The user who is being blocked by `user`.
    """
    user = models.ForeignKey(
        MoogtMedaUser,
        related_name='blockings',
        null=False, on_delete=models.CASCADE
    )

    blocked_user = models.ForeignKey(
        MoogtMedaUser,
        related_name='blockers',
        null=False,
        on_delete=models.CASCADE
    )

    def clean(self) -> None:
        if self.user == self.blocked_user:
            raise ValidationError('You cannot block yourself.')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'blocked_user'), name='unique_constraint')
        ]
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.blocked_user} blocked by {self.user}'


comment_was_posted.connect(Activity.new_comment_recorder)

class AccountReport(BaseReport):
    # The user this report is made for.
    user = models.ForeignKey(MoogtMedaUser, related_name='reports', null=False, blank=False, on_delete=models.CASCADE)
    
    def reported_on(self):
        return self.user
    
    def item_created_at(self):
        return self.user.date_joined
    
    def __str__(self) -> str:
        return str(self.user)
    

class PhoneNumber(Timestampable):
    """A phone number for a user account."""
    firebase_uid = models.CharField(
        null=False, 
        unique=True,
        error_messages={
            'unique': "A user already exists.",
        },
        max_length=50
    )
    
    is_verified = models.BooleanField(default=False, null=False, blank=True)

    phone_number = models.CharField(
        null=False, 
        unique=True,    
        error_messages={
            'unique': "A user with that phone number already exists.",
        },
        max_length=15
    )
    
    user = models.OneToOneField(MoogtMedaUser, related_name='phone_number', null=False, on_delete=models.CASCADE)
