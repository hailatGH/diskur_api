import datetime

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.urls import reverse
from django.utils import timezone
from model_utils.models import SoftDeletableModel

from api.enums import Visibility
from api.models import ShareStats, Tag
from meda.behaviors import Timestampable, Taggable
from .enums import ActivityStatus
from model_utils import Choices


class Score(models.Model):
    """An abstract model that defines common fields used by other classes."""

    # A constant used for trend calculations.
    TRENDING_DURATION_HOURS = 12

    # The minimum score an item must have in order to be considered trending.
    TRENDING_MINIMUM_SCORE = 0

    # The current score of this item. It will increase when users make reactions to it.
    score_now = models.DecimalField(default=0, max_digits=11, decimal_places=2)

    # The score of the item X duration(where X is a time duration that we control) ago.
    score_before = models.DecimalField(
        default=0, max_digits=11, decimal_places=2)

    # The last time the score was updated.
    score_last_updated_at = models.DateTimeField(default=timezone.now)

    # The overall score of the item since it's creation, which will increase whenever reactions are made to it.
    overall_score = models.DecimalField(
        default=0, max_digits=11, decimal_places=2)

    class Meta:
        abstract = True

    def _can_score_be_updated(self):
        """
        Decide whether or not the score of this item should be updated.
        """
        return (timezone.now() - self.score_last_updated_at) > datetime.timedelta(hours=self.TRENDING_DURATION_HOURS)

    def calculate_score(self):
        pass

    def maybe_update_score(self):
        score = self.calculate_score()
        if self._can_score_be_updated():
            self.score_before = self.score_now
            self.score_now = score

        self.overall_score = score
        self.save()


class Stats(models.Model):
    """
    Abstract model for storing stats data about items.
    """
    share_stats = GenericRelation(
        ShareStats, content_type_field='content_type', object_id_field='object_id')

    class Meta:
        abstract = True

    def update_share_count(self, provider, count, content_type):
        """
        Update the share count for this moogt stats.
        :param provider: The type of the platform. e.g., facebook
        :param count: The share count for this share provider.
        :param content_type: The content type object for the model.
        :return:
        """
        obj, created = ShareStats.objects.get_or_create(provider=provider,
                                                        content_type_id=content_type.pk,
                                                        object_id=self.pk)

        obj.share_count = count
        obj.save()

    def get_share_count(self):
        count = 0
        for stat in self.share_stats.all():
            count += stat.share_count
        return count


class BaseModel(SoftDeletableModel):
    # The list of tags for the content.
    tags = models.ManyToManyField(Tag, blank=True)

    # Whether or not this content is for the public or for the user's followers. Default is for the public.
    visibility = models.CharField(default=Visibility.PUBLIC.name,
                                  max_length=15,
                                  choices=[(status.name, status.value) for status in Visibility])

    # The date/time when this content was created.
    created_at = models.DateTimeField(default=timezone.now)

    # The last update time for this content.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def add_tags(self, tags):
        for t in tags:
            self.tags.add(t)


class AbstractActivity(Timestampable):
    # The Current status of this Moogt or Argument card
    status = models.CharField(default=ActivityStatus.PENDING.value,
                              max_length=15,
                              choices=[(status.value, status.name) for status in ActivityStatus])

    # The user that is responsible for the creation of this activity
    user = models.ForeignKey('users.MoogtMedaUser',
                             related_name='+',
                             null=True,
                             on_delete=models.SET_NULL)

    # The user that is responsible for the action of this activity
    actor = models.ForeignKey('users.MoogtMedaUser',
                              related_name='+',
                              null=True,
                              on_delete=models.SET_NULL)

    class Meta:
        abstract = True


class TimestampableMock(Timestampable, models.Model):
    """This model is only for testing."""
    pass


class TaggableMock(Taggable, models.Model):
    """This model is only for testing."""
    pass


class BaseReport(Timestampable):
    PENDING = 'PEN'
    ITEM_DELETED = 'DEL'
    USER_WARNED = 'WAR'
    ACCOUNT_DEACTIVATED = 'DEC'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (ITEM_DELETED, 'Item Deleted'),
        (USER_WARNED, 'User Warned'),
        (ACCOUNT_DEACTIVATED, 'Account Deactivated'),
    ]

    # The link that will open the item being reported.
    link = models.URLField(max_length=1000, null=True,
                           blank=True, default=None)

    # The user who made the report.
    reported_by = models.ForeignKey('users.MoogtMedaUser',
                                    related_name='+',
                                    null=False,
                                    blank=False,
                                    on_delete=models.CASCADE)

    # Why was this report made.
    reason = models.CharField(max_length=200,
                              blank=False,
                              null=False)

    # Who took the action.
    action_taken_by = models.ForeignKey('users.MoogtMedaUser',
                                        related_name='+',
                                        null=True,
                                        blank=True,
                                        on_delete=models.CASCADE)

    # Additional info provided by [action_taken_by].
    remark = models.CharField(max_length=1000, null=True, blank=False)

    # The state of the report.
    status = models.CharField(
        max_length=3, default=PENDING, choices=STATUS_CHOICES)

    class Meta:
        abstract = True

    def reported_on(self):
        pass

    def item_created_at(self):
        pass


class AbstractActivityAction(Timestampable):
    ACTION_TYPES = Choices('decline', 'cancel', 'approve', 'waiting')

    actor = models.ForeignKey(
        "users.MoogtMedaUser", related_name='+', on_delete=models.CASCADE)
    action_type = models.CharField(
        choices=ACTION_TYPES, max_length=20, default=ACTION_TYPES.waiting, null=False, blank=False)

    class Meta:
        abstract = True
