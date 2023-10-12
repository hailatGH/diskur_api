from annoying.fields import AutoOneToOneField
from django.contrib.contenttypes.fields import ContentType, GenericRelation
from django.db import models
from django.utils import timezone
from rest_framework.serializers import ValidationError

from meda.models import BaseReport, Score, Stats, BaseModel
from polls.managers import PollOptionManager, PollManager, PollQuerySet
from users.models import MoogtMedaUser
from notifications.models import Notification


# Create your models here.
# Poll model class
class Poll(BaseModel):
    """
    Represents a poll
    """

    # Person creating the poll
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='polls',
                             null=True,
                             on_delete=models.SET_NULL)

    # Question of the poll
    title = models.CharField(max_length=280)

    # The date when the poll will start
    start_date = models.DateTimeField(blank=True,
                                      default=timezone.now)

    # The date when the poll will end
    end_date = models.DateTimeField(null=True,
                                    blank=True,
                                    default=None)

    # The maximum amount of time that the poll will be active
    max_duration = models.DurationField(default=timezone.timedelta(days=1))

    # The number of comments made to this view
    comment_count = models.IntegerField(default=0)

    # Whether or not the poll is closed. i.e., the poll will receive votes only if it's not closed.
    is_closed = models.BooleanField(default=False)

    # The related field for notifications
    notifications = GenericRelation(Notification, 
                                    related_query_name='target_poll',
                                    content_type_field='target_content_type',
                                    object_id_field='target_object_id',)

    objects = PollManager.from_queryset(PollQuerySet)()

    def __str__(self):
        return self.title[:50]

    def get_is_closed(self):
        return self.is_closed

    def set_is_closed(self, value):
        self.is_closed = value

    def has_user_voted(self, user):
        for option in self.options.all():
            user_voted = option.votes.filter(id=user.id).exists()
            if user_voted:
                return True
        return False

    def total_voters(self):
        return self.total_vote

    def has_expired(self):
        if self.end_date is None:
            return True

        return self.end_date < timezone.now()

    def overall_clock_time_remaining(self):
        if self.has_expired():
            return timezone.timedelta(0)

        overall_time_left = self.end_date - timezone.now()
        return overall_time_left

    def calculate_score(self):
        """
        This is a linear function that calculates the score for a poll based on the params:
           - vote count
        """
        vote_pts = self.total_voters()

        return vote_pts

    def create_options(self, option_array):
        if len(option_array) > 4 or len(option_array) < 2:
            raise ValidationError("Options can not be less than 2 or greater than 4.")

        self.options.bulk_create([PollOption(poll=self, content=option.get('content')) for option in option_array])
    
    def comments_count(self):
        return self.comment_count


class PollOption(models.Model):
    """
    Represents the options that a poll consisits
    """

    # Associated Poll for this option 
    poll = models.ForeignKey(Poll,
                             related_name='options',
                             null=True,
                             on_delete=models.SET_NULL)

    # Represents the content of the option for a poll
    content = models.CharField(max_length=50)

    # Contains the users who voted on this specific option 
    # on a poll
    votes = models.ManyToManyField(MoogtMedaUser,
                                   blank=True,
                                   related_name='+')
    objects = PollOptionManager()

    def win_percentage(self):
        votes_count = self.vote_count
        total_votes_count = self.poll.total_voters()

        if total_votes_count == 0:
            return 0

        return int(100 * votes_count / total_votes_count)

    def has_user_voted(self, user):
        return self.votes.filter(id=user.id).exists()


class PollStats(Stats):
    # The poll that is linked to this stats
    poll = AutoOneToOneField(Poll,
                             related_name='stats',
                             primary_key=True,
                             on_delete=models.CASCADE)

    def func_update_share_count(self, provider, count):
        """
        Update the share count for this poll stats.
        :param provider: The type of the platform. e.g., facebook
        :param count: The share count for this share provider.
        :return:
        """
        moogt_stat_type = ContentType.objects.get_for_model(PollStats)
        super().update_share_count(provider, count, moogt_stat_type)

    def func_get_share_count(self):
        return self.get_share_count()


class PollScore(Score):
    # The poll associated with this score object.
    poll = AutoOneToOneField(Poll,
                             related_name='score',
                             primary_key=True,
                             on_delete=models.CASCADE)

    def calculate_score(self):
        return self.poll.calculate_score()
    
    
class PollReport(BaseReport):
    # The poll this report is made for.
    poll = models.ForeignKey(Poll, related_name='reports', null=False, blank=False, on_delete=models.CASCADE)

    def reported_on(self):
        return self.poll.user
    
    def item_created_at(self):
        return self.poll.created_at
    
    def __str__(self) -> str:
        return str(self.poll)