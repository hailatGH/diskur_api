import math
from datetime import timedelta

from annoying.fields import AutoOneToOneField
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, SuspiciousOperation
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from model_utils import Choices

from api.enums import Visibility
from arguments.models import Argument
from meda.behaviors import Timestampable, Taggable
from meda.enums import MoogtEndStatus, MoogtType, ArgumentType, ActivityStatus
from meda.models import BaseReport, Score, Stats, BaseModel, AbstractActivity, AbstractActivityAction
from moogts.enums import MiniSuggestionState, MoogtActivityType, DonationLevel, MoogtWebsocketMessageType
from moogts.managers import MoogtManager, MoogtQuerySet, DonationManager, MoogtStatusManager, MoogtActivityManager

from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from users.models import MoogtMedaUser


class MoogtBanner(models.Model):
    """A model representing an uploaded banner for a moogt."""

    banner = models.ImageField(upload_to='banners', null=False)


class Moogt(BaseModel):
    """A model representing a full debate (moogt)."""

    # The central statement which is being debated. Supplied by the
    # 'proposition' at creation time.
    # TODO: The character limit is temporary. It should be configurable in the
    # future.
    
    # Custom field added
    numberOfCard = models.IntegerField(default=1,
        validators=[
            MinValueValidator(0, message='Value must be greater than or equal to 0.'),
            MaxValueValidator(100, message='Value must be less than or equal to 100.')
        ]
    )
    
    resolution = models.CharField(max_length=200)

    # Text giving a brief description about the Moogt.
    description = models.CharField(max_length=560, null=True, blank=True)

    # The user who initiated the debate by supplying a 'resolution'. The
    # 'proposition' always debates in support of the 'resolution'.
    # SET_NULL means deletion of the user will not cascade down to delete the
    # Moogt. This requires null=True.
    proposition = models.ForeignKey(MoogtMedaUser,
                                    related_name='proposition_moogts',
                                    null=True,
                                    on_delete=models.SET_NULL)

    # The user debating in opposition of the 'resolution'.
    # Initially, there is no opposition as a user must join an existing Moogt
    # as the opposition. This requires setting blank=True.
    # on_delete=SET_NULL means deletion of the user will not cascade down to
    # delete the Moogt. This requires setting null=True.
    opposition = models.ForeignKey(MoogtMedaUser,
                                   related_name='opposition_moogts',
                                   blank=True,
                                   null=True,
                                   on_delete=models.SET_NULL)

    # The user moderating this moogt
    moderator = models.ForeignKey(MoogtMedaUser,
                                  related_name='moderating_moogts',
                                  blank=True,
                                  null=True,
                                  on_delete=models.SET_NULL)

    # If true, then it's the 'proposition' user's turn to add an argument to the Moogt.
    # Otherwise, it's the 'opposition' user's turn to add an argument.
    next_turn_proposition = models.BooleanField(default=True)

    # If true, then it's the 'proposition' that added an argument(or waived turn) last. Otherwise,
    # it's the 'opposition' that went last.
    last_posted_by_proposition = models.BooleanField(default=False)

    # Whether or not this debate has ended. In order for a moogt to end, first
    # one of the moogter have to request to end the debate which sets
    # |end_requested| to true. And optionally may give the other moogter the
    # last word.
    has_ended = models.BooleanField(default=False)

    # Whether or not either the proposition or the opposition have requested
    # to end the debate.
    end_requested = models.BooleanField(default=False)

    # If True, then the proposition is the one who requested to end the debate.
    # Otherwise the opposition is the one who requested to end the debate.
    # NOTE: This field is only meaningful if |end_requested| is True.
    end_requested_by_proposition = models.BooleanField(default=False)

    # Whether or not this is a premiering moogt or not.
    is_premiering = models.BooleanField(default=False)

    # The date/time this moogt is scheduled to start.
    premiering_date = models.DateTimeField(
        auto_now=False, null=True, blank=True)

    # If the debate has ended, what is the ending status?
    # NOTE: This field is only meaningful if |end_requested| is True.
    end_request_status = models.CharField(
        default=None,
        null=True,
        max_length=4,
        choices=[(status.name, status.value) for status in MoogtEndStatus])

    # Whether or not this is duo or group moogt. Default is duo moogt.
    type = models.CharField(default=MoogtType.DUO.name,
                            max_length=56,
                            choices=[(t.name, t.value) for t in MoogtType])

    # The time that a moogt starts. This is precisely the time that an opposition
    # accepts/joins the moogt.
    started_at = models.DateTimeField(auto_now=False, null=True, blank=True)

    # The time when the latest argument was added to this moogt. Initially, this should
    # be the same as |created_at|.
    latest_argument_added_at = models.DateTimeField(default=timezone.now)

    # The maximum amount of time that the debate will be active after starting
    # (i.e. since |started_at|). After this duration expires, the moogt will
    # be closed.
    max_duration = models.DurationField(null=True)

    # The maximum amount of time spent waiting for a moogter to respond with their
    # argument (i.e. since |latest_argument_added_at|). If this timer expires before
    # submitting a response, the moogter forfeits their turn.
    idle_timeout_duration = models.DurationField(
        default=timezone.timedelta(hours=1))

    # A concise summary of the moogt with an image, which is optional
    banner = models.OneToOneField(MoogtBanner,
                                  related_name='moogt',
                                  null=True,
                                  on_delete=models.SET_NULL)

    # Whether or not this moogt is paused.
    is_paused = models.BooleanField(default=False)

    # The time that a moogt pause request has been approved.
    paused_at = models.DateTimeField(auto_now=False, null=True, blank=True)

    # The time that a moogt resume request has been approved.
    resumed_at = models.DateTimeField(auto_now=False, null=True, blank=True)

    # The user that accepted a resume request
    resumed_by = models.ForeignKey(MoogtMedaUser,
                                   related_name='+',
                                   blank=True,
                                   null=True,
                                   on_delete=models.SET_NULL)

    # The user that accepted a pause request
    paused_by = models.ForeignKey(MoogtMedaUser,
                                  related_name='+',
                                  blank=True,
                                  null=True,
                                  on_delete=models.SET_NULL)

    # The user that quit this moogt
    quit_by = models.ForeignKey(MoogtMedaUser,
                                related_name='+',
                                blank=True,
                                null=True,
                                on_delete=models.SET_NULL)

    # The related field for notifications
    notifications = GenericRelation(Notification,
                                    related_query_name='target_moogt',
                                    content_type_field='target_content_type',
                                    object_id_field='target_object_id', )

    # A custom model manager for the Moogt model
    objects = MoogtManager.from_queryset(MoogtQuerySet)()

    def __str__(self):
        if self.resolution == None:
            return ''
        if len(self.resolution) > 30:
            return f'{self.resolution[:30]}...'

        return self.resolution

    def func_has_started(self):
        return self.get_opposition() is not None and self.get_started_at() is not None

    def func_has_expired(self):
        if not self.func_has_started():
            return False

        if self.get_is_paused():
            return False
        # This means the moogt is indefinite, so it won't ever expire.
        if not self.get_max_duration():
            return False

        if not self.get_resumed_at():
            return (self.get_started_at() + self.get_max_duration()) < timezone.now()

        return (self.get_started_at() + self.get_max_duration() + (
                self.get_resumed_at() - self.get_paused_at())) < timezone.now()

    def func_expire_time(self):
        if not self.func_has_started():
            raise ValidationError("Moogt has not started yet.")

        if not self.get_max_duration():
            return None

        if not self.get_resumed_at():
            return self.get_started_at() + self.get_max_duration()

        return self.get_started_at() + self.get_max_duration() + (self.get_resumed_at() - self.get_paused_at())

    def func_overall_clock_time_remaining(self):
        if not self.func_has_started():
            raise ValidationError('Moogt has not started.')

        if self.func_has_ended_or_expired():
            return timezone.timedelta(0)

        if not self.get_max_duration():
            return None

        if self.get_is_paused():
            return (self.get_started_at() + self.get_max_duration()) - self.get_paused_at()

        overall_time_left = self.func_expire_time() - timezone.now()
        return overall_time_left

    def func_idle_timer_expire_time_remaining(self):
        if not self.get_started_at():
            return (timezone.now() + self.get_idle_timeout_duration()) - timezone.now()

        if self.get_is_paused() and self.get_paused_at():
            expire_time_left = (self.get_latest_argument_added_at() + self.get_idle_timeout_duration()
                                ) - self.get_paused_at()
            return expire_time_left

        expire_time_left = (self.get_latest_argument_added_at() +
                            self.get_idle_timeout_duration()) - timezone.now()
        # In case it's already expired, do not return
        # negative value.
        if expire_time_left.total_seconds() < 0:
            return timezone.timedelta(0)

        return expire_time_left

    def func_create_moogt_started_status(self):
        if self.func_has_started() and not self.is_premiering and self.statuses.count() == 0:
            moogt_started = MoogtStatus(
                status=MoogtStatus.STATUS.started, moogt=self)
            moogt_started.save()

    def func_update_premiering_field(self):
        with transaction.atomic():
            from .serializers import MoogtNotificationSerializer
            if self.is_premiering and self.premiering_date and timezone.now() > self.premiering_date:
                self.is_premiering = False
                self.started_at = self.premiering_date
                self.save()

                notify.send(
                    recipient=MoogtMedaUser.objects.filter(
                        Q(id=self.opposition.pk) | Q(id=self.proposition.pk)),
                    sender=self.proposition,
                    verb="premiering",
                    target=self,
                    type=NOTIFICATION_TYPES.moogt_status,
                    send_email=False,
                    send_telegram=True,
                    data={'moogt': MoogtNotificationSerializer(self).data})

    def func_end_moogt(self):
        if not self.get_has_ended() and \
                self.func_has_expired():
            self.func_create_moogt_over_status()

        moogt_over = MoogtStatus.objects.filter(
            moogt=self, status=MoogtStatus.STATUS.duration_over).first()
        if moogt_over:
            if self.arguments.filter(created_at__gt=moogt_over.created_at, user=self.opposition).exists():
                self.set_has_ended(True)
                self.save()

    def func_skip_expired_turns(self):
        # This method can potentially mutate the moogt by creating Arguments
        # and attaching them to it. If multiple viewers open a moogt at the
        # same time, it would create multiple concurrent updates.
        # The following ensures that the moogt row is locked until either
        # one of the views finishes updating.
        with transaction.atomic():
            # Lock this moogt while updates are happening below.
            self_moogt = Moogt.available_objects.select_for_update().get(id=self.id)
            # Check before creating expired turns. If any of the following cases are true,
            # then simply break out of this function without doing anything.
            if not self.func_has_started() or self.get_is_paused() or self.get_has_ended():
                return

            curr_user = self.get_proposition(
            ) if self.get_next_turn_proposition() else self.get_opposition()
            time_since_last_post = self.func_get_time_since_last_post()
            num_of_expired_turns = int(
                time_since_last_post.total_seconds() // self.get_idle_timeout_duration().total_seconds())
            max_allowed_turns = math.ceil(self.func_get_max_inactive_duration(
            ).total_seconds() / self.get_idle_timeout_duration().total_seconds())

            last_activity_added_at = self.func_get_last_activity_added_at()
            if num_of_expired_turns >= max_allowed_turns:
                num_of_expired_turns = max_allowed_turns
                self.func_pause_moogt(curr_user,
                                      last_activity_added_at + (
                                          num_of_expired_turns * self.get_idle_timeout_duration()))
                MoogtStatus.objects.create(
                    status=MoogtStatus.STATUS.auto_paused, moogt=self)

                from .serializers import MoogtNotificationSerializer

                notify.send(
                    recipient=MoogtMedaUser.objects.filter(
                        Q(id=self.opposition.pk) | Q(id=self.proposition.pk)),
                    sender=self.proposition,
                    verb="auto paused",
                    target=self,
                    type=NOTIFICATION_TYPES.moogt_status,
                    send_email=False,
                    send_telegram=True,
                    data={'moogt': MoogtNotificationSerializer(self).data},
                    push_notification_title='Your Moogt got Auto-Paused',
                    push_notification_description=f'Your Moogt, "{self}" got auto-paused due to inactivity.'
                )

            if num_of_expired_turns > 0:
                self.func_create_expired_turn_argument(
                    curr_user, num_of_expired_turns)
                self.set_latest_argument_added_at(
                    last_activity_added_at + (num_of_expired_turns * self.get_idle_timeout_duration()))
                if num_of_expired_turns % 2 != 0:
                    self.set_next_turn_proposition(
                        self.get_last_posted_by_proposition())
                else:
                    self.set_next_turn_proposition(
                        not self.get_last_posted_by_proposition())
                self.save()

    def func_get_time_since_last_post(self):
        latest_added_at = self.func_get_last_activity_added_at()

        if self.func_has_expired():
            return self.func_expire_time() - latest_added_at
        return timezone.now() - latest_added_at

    def func_get_last_activity_added_at(self):
        latest_added_at = self.get_latest_argument_added_at()

        missed_turn: Argument = self.func_get_last_argument()
        if missed_turn and missed_turn.type == ArgumentType.MISSED_TURN.name:
            latest_added_at = latest_added_at - (
                missed_turn.consecutive_expired_turns_count * self.get_idle_timeout_duration())

        return latest_added_at

    def func_is_pausable(self, missed_turn):
        inactive_duration = self.func_inactive_duration(missed_turn)
        if inactive_duration:
            return (self.get_idle_timeout_duration() <= timedelta(minutes=3) and inactive_duration >= timedelta(
                hours=3)) or \
                (self.get_idle_timeout_duration() <= timedelta(minutes=30) and inactive_duration >= timedelta(
                    hours=6)) or \
                (self.get_idle_timeout_duration() <= timedelta(hours=1) and inactive_duration >= timedelta(
                    hours=12)) or \
                (self.get_idle_timeout_duration() <= timedelta(hours=3) and inactive_duration >= timedelta(
                    hours=24)) or \
                (self.get_idle_timeout_duration() <= timedelta(hours=6) and inactive_duration >= timedelta(
                    hours=48)) or \
                (self.get_idle_timeout_duration() <= timedelta(days=1) and inactive_duration >= timedelta(
                    weeks=1)) or \
                (self.get_idle_timeout_duration() <= timedelta(days=3) and inactive_duration >= timedelta(
                    weeks=2)) or \
                (self.get_idle_timeout_duration() <= timedelta(weeks=1) and inactive_duration >= timedelta(
                    weeks=4)) or \
                (inactive_duration >= timedelta(weeks=4))

        return False

    def func_inactive_duration(self, missed_turn):
        if missed_turn.type == ArgumentType.MISSED_TURN.name:
            return self.latest_argument_added_at - missed_turn.created_at + self.get_idle_timeout_duration()

    def func_expire_moogt_activities(self):
        # This method will make all the PENDING activities of a moogt expire if the moogt has
        # ended but excludes when the moogt is trying to request delete
        has_ended_or_expired = self.func_has_ended_or_expired()
        if has_ended_or_expired:
            self.activities.filter(status=ActivityStatus.PENDING.value).exclude(type=MoogtActivityType.DELETE_REQUEST.value).update(
                status=ActivityStatus.EXPIRED.value)

        return has_ended_or_expired

    def func_create_expired_turn_argument(self, curr_user, turns_count):
        missed_turn: Argument = self.func_get_last_argument()
        created_at_time = self.get_latest_argument_added_at() + \
            self.get_idle_timeout_duration()

        if not missed_turn or missed_turn.type != ArgumentType.MISSED_TURN.name:
            empty_argument = Argument(type=ArgumentType.MISSED_TURN.name)
            empty_argument.moogt = self
            empty_argument.user = curr_user
            empty_argument.created_at = created_at_time
            empty_argument.consecutive_expired_turns_count = turns_count
            empty_argument.save()
        else:
            missed_turn.consecutive_expired_turns_count = turns_count
            missed_turn.save()

    def func_get_last_argument(self) -> Argument:
        last_bundle = self.bundles.filter(
            created_at__lt=timezone.now()).order_by('-created_at').first()
        last_status = self.statuses.filter(
            created_at__lt=timezone.now()).order_by('-created_at').first()
        last_argument = self.arguments.filter(
            created_at__lt=timezone.now()).order_by('-created_at').first()

        if last_argument:
            last_argument_after_bundle = True if last_bundle is None else last_argument.created_at > last_bundle.created_at
            last_argument_after_status = True if last_status is None else last_argument.created_at > last_status.created_at
            if last_argument_after_bundle and last_argument_after_status:
                return last_argument

    def func_has_ended_or_expired(self):
        has_ended = self.get_has_ended()
        has_expired = self.func_has_expired()

        if has_expired:
            self.func_create_moogt_over_status()

        return has_ended or has_expired

    def func_create_moogt_over_status(self):
        from moogts.serializers import MoogtNotificationSerializer
        if self.statuses.filter(
                Q(status=MoogtStatus.STATUS.broke_off) |
                Q(status=MoogtStatus.STATUS.ended) |
                Q(status=MoogtStatus.STATUS.duration_over)).count() == 0:
            moogt_over = MoogtStatus(
                moogt=self, status=MoogtStatus.STATUS.duration_over)
            moogt_over.save()

            notify.send(
                recipient=MoogtMedaUser.objects.filter(
                    Q(id=self.opposition.pk) | Q(id=self.proposition.pk)),
                sender=self.proposition,
                verb="duration over",
                target=self,
                type=NOTIFICATION_TYPES.moogt_status,
                send_email=False,
                send_telegram=True,
                data={'moogt': MoogtNotificationSerializer(self).data})

    def func_ended_by(self):
        if not self.get_end_requested():
            return None
        if self.get_end_requested_by_proposition():
            return self.get_proposition()
        else:
            return self.get_opposition()

    def func_end_status(self):
        if not self.get_end_requested():
            return None
        return MoogtEndStatus[self.get_end_request_status()].value

    def func_start(self, user):
        if self.func_has_started():
            raise ValidationError("Moogt already started.")

        self.set_opposition(user)
        now = timezone.now()
        self.set_started_at(now)
        # Since argument has been added by the proposition and now an opposition
        # is set for the moogt, we set latest_argument_added_at to now
        self.set_latest_argument_added_at(now)
        self.save()

    def func_update_moogt(self, user, debate_status=None):
        self.set_next_turn_proposition(user != self.get_proposition())
        self.set_last_posted_by_proposition(
            not self.get_next_turn_proposition())
        self.set_latest_argument_added_at(timezone.now())

        if not self.get_has_ended():
            if debate_status != "continue":
                self.set_end_requested(True)
                self.set_end_requested_by_proposition(
                    user == self.get_proposition())
                if debate_status == 'concede':
                    self.set_end_request_status(MoogtEndStatus.concede())
                    self.set_has_ended(False)
                elif debate_status == 'disagree':
                    self.set_end_request_status(MoogtEndStatus.disagree())
                else:
                    raise SuspiciousOperation("Invalid End Request Status.")

        self.save()

    def func_is_participant(self, user):
        return user == self.get_proposition() or user == self.get_opposition() or user == self.get_moderator()

    def func_is_current_turn(self, user):
        if self.func_is_participant(user):
            if self.get_moderator() == user:
                return True
            elif self.get_started_at() is None:
                return True
            elif self.get_proposition() == user:
                return self.get_next_turn_proposition()
            elif self.get_opposition() == user:
                return not self.get_next_turn_proposition()

        return False

    def func_get_max_inactive_duration(self):
        """Gets the maximum allowed inactive duration, i.e., without activity"""
        max_duration = self.get_max_duration()
        # This means this moogt is not indefinite
        if max_duration:
            # The max inactive duration is 1/4 of the overall moogt duration
            return self.get_max_duration() / 4

        # The moogt must be indefinite, the max_inactive_duration is calculated differently
        idle_timeout_duration = self.get_idle_timeout_duration()
        if idle_timeout_duration <= timedelta(minutes=3):
            return timedelta(hours=3)
        elif idle_timeout_duration <= timedelta(minutes=30):
            return timedelta(hours=6)
        elif idle_timeout_duration <= timedelta(hours=1):
            return timedelta(hours=12)
        elif idle_timeout_duration <= timedelta(hours=3):
            return timedelta(hours=24)
        elif idle_timeout_duration <= timedelta(hours=6):
            return timedelta(hours=48)
        elif idle_timeout_duration <= timedelta(days=1):
            return timedelta(weeks=1)
        elif idle_timeout_duration <= timedelta(days=3):
            return timedelta(weeks=2)
        else:
            return timedelta(weeks=4)

    def get_opponent(self, user):
        if self.func_is_participant(user):
            return self.proposition if self.opposition == user else self.opposition

    def get_user_to_take_action(self, userOne, userTwo):
        users = [userOne, userTwo]
        return users

    def applauds_count(self):
        count = 0
        for argument in self.arguments.all():
            count += argument.stats.applauds_count()
        return count

    def unread_cards_count(self, user):
        read_by = user.read_moogts.filter(moogt=self).first()
        if read_by:
            count = self.arguments \
                .filter(Q(created_at__gt=read_by.latest_read_at)) \
                .filter(Q(type=ArgumentType.NORMAL.name) | Q(type=ArgumentType.MODERATOR_ARGUMENT.name) | Q(type=ArgumentType.CONCLUDING.name)) \
                .count()

            return count

    def calculate_score(self):
        """
        This is a linear function that calculates the score for a moogt based on the params:
        """
        # TODO(nebiyu): Adjust linear coefficients appropriately.
        # applaud_score = self.applauds_count()
        follower_score = self.followers.count()
        return follower_score

    def func_pause_moogt(self, user=None, paused_at=None):
        self.set_paused_at(paused_at)
        self.set_paused_by(user)
        self.set_is_paused(True)

        return self.get_paused_at()

    def func_resume_moogt(self, user):
        now = timezone.now()

        if not self.get_is_paused():
            return False

        self.set_resumed_at(now)
        self.set_resumed_by(user)
        self.set_is_paused(False)

        self.set_latest_argument_added_at(
            now - (self.get_paused_at() - self.get_latest_argument_added_at()))

        return self.get_resumed_at()

    # This method must be named this way (does not start with func_).
    # It is implementing django's standard method:
    # https://docs.djangoproject.com/en/2.2/ref/models/instances/#get-absolute-url
    def get_absolute_url(self):
        return reverse('meda:detail', args=[self.id])

    def func_title(self):
        return self.get_resolution()[:30]

    def get_resolution(self):
        return self.resolution

    def set_resolution(self, value):
        self.resolution = value

    def get_proposition(self):
        return self.proposition

    def set_proposition(self, value):
        self.proposition = value

    def get_created_at(self):
        return self.created_at

    def set_created_at(self, value):
        self.created_at = value

    def get_updated_at(self):
        return self.updated_at

    def set_updated_at(self, value):
        self.updated_at = value

    def get_opposition(self):
        return self.opposition

    def set_opposition(self, value):
        self.opposition = value

    def get_next_turn_proposition(self):
        return self.next_turn_proposition

    def set_next_turn_proposition(self, value):
        self.next_turn_proposition = value

    def get_last_posted_by_proposition(self):
        return self.last_posted_by_proposition

    def set_last_posted_by_proposition(self, value):
        self.last_posted_by_proposition = value

    def get_end_request_status(self):
        return self.end_request_status

    def set_end_request_status(self, value):
        self.end_request_status = value

    def get_end_requested(self):
        return self.end_requested

    def set_end_requested(self, value):
        self.end_requested = value

    def get_end_requested_by_proposition(self):
        return self.end_requested_by_proposition

    def set_end_requested_by_proposition(self, value):
        self.end_requested_by_proposition = value

    def get_has_ended(self):
        return self.has_ended

    def set_has_ended(self, value):
        self.has_ended = value

    def get_idle_timeout_duration(self):
        return self.idle_timeout_duration

    def set_idle_timeout_duration(self, value):
        self.idle_timeout_duration = value

    def get_latest_argument_added_at(self):
        return self.latest_argument_added_at

    def set_latest_argument_added_at(self, value):
        self.latest_argument_added_at = value

    def get_started_at(self):
        return self.started_at

    def set_started_at(self, value):
        self.started_at = value

    def get_max_duration(self):
        return self.max_duration

    def set_max_duration(self, value):
        self.max_duration = value

    def set_is_paused(self, value):
        self.is_paused = value

    def get_is_paused(self):
        return self.is_paused

    def set_paused_at(self, value):
        self.paused_at = value

    def get_paused_at(self):
        return self.paused_at

    def set_resumed_at(self, value):
        self.resumed_at = value

    def get_resumed_at(self):
        return self.resumed_at

    def set_paused_by(self, value):
        self.paused_by = value

    def get_paused_by(self):
        return self.paused_by

    def set_resumed_by(self, value):
        self.resumed_by = value

    def get_resumed_by(self):
        return self.resumed_by

    def get_moderator(self):
        return self.moderator

    def set_moderator(self, value):
        self.moderator = value

    def get_quit_by(self):
        return self.quit_by

    def set_quit_by(self, value):
        self.quit_by = value


class MoogtMiniSuggestion(Timestampable, Taggable):
    # The moogt that this suggestion belongs to
    moogt = models.ForeignKey(Moogt,
                              related_name="mini_suggestions",
                              null=True,
                              on_delete=models.SET_NULL)

    # The suggested child of this mini suggestion.
    suggested_child = models.OneToOneField('self',
                                           related_name='edited_parent',
                                           null=True,
                                           on_delete=models.SET_NULL)

    # The user that made this suggestion
    user = models.ForeignKey(MoogtMedaUser,
                             related_name="+",
                             null=True,
                             on_delete=models.SET_NULL)

    # The user moderating this moogt
    moderator = models.ForeignKey(MoogtMedaUser,
                                  blank=True,
                                  null=True,
                                  related_name="+",
                                  on_delete=models.SET_NULL)

    # The suggested resolution of the moogt
    resolution = models.CharField(max_length=200, null=True)

    # Text giving a brief description about the Moogt.
    description = models.CharField(max_length=560, null=True, blank=True)

    # The suggested duration of the moogt
    max_duration = models.DurationField(null=True)

    # The suggested reply time duration of the moogt
    idle_timeout_duration = models.DurationField(null=True)

    # The suggested visibility of the moogt
    visibility = models.CharField(max_length=15,
                                  null=True,
                                  choices=[(status.name, status.value) for status in Visibility])

    # The date/time this moogt is scheduled to start.
    premiering_date = models.DateTimeField(
        auto_now=False, null=True, blank=True)

    # Whether or not you're suggesting to stop the countdown timer for a premiering moogt.
    stop_countdown = models.BooleanField(default=False)

    banner = models.OneToOneField(MoogtBanner,
                                  related_name='+',
                                  null=True,
                                  on_delete=models.SET_NULL)

    # whether or not you're suggesting to remove the banner of a moogt
    remove_banner = models.BooleanField(default=False)

    state = models.CharField(max_length=15,
                             default=MiniSuggestionState.PENDING.value,
                             choices=[(status.name, status.value) for status in MiniSuggestionState])

    def approve(self, sender):
        from .serializers import MoogtMiniSuggestionSerializer, MoogtNotificationSerializer
        from notifications.models import Notification

        notification_sent = False
        recipients = MoogtMedaUser.objects.filter(id=self.user.id)

        for field in MoogtMiniSuggestionSerializer.allowed_fields:
            value = getattr(self, field)

            if field == 'stop_countdown' and value is not None:
                self.moogt.premiering_date = None
                self.moogt.save()
                self.state = MiniSuggestionState.APPROVED.value
                self.save()
                break

            elif field == 'remove_banner':
                self.moogt.banner = None
                self.moogt.save()
                self.state = MiniSuggestionState.APPROVED.value
                self.save()

            elif field == 'tags':
                if self.tags.count() > 0:
                    self.state = MiniSuggestionState.APPROVED.value
                    self.moogt.tags.add(*self.tags.all())
                    self.save()

            else:
                if value is not None:
                    setattr(self.moogt, field, value)
                    if field == 'premiering_date':
                        self.moogt.is_premiering = True

                        notification_sent = True
                        recipients = recipients | self.moogt.opposition.followers.all(
                        ) | self.moogt.proposition.followers.all()

                        notify.send(recipient=recipients,
                                    sender=sender,
                                    verb="premiering",
                                    send_email=False,
                                    send_telegram=True,
                                    type=NOTIFICATION_TYPES.moogt_premiere,
                                    category=Notification.NOTIFICATION_CATEGORY.normal,
                                    target=self.moogt,
                                    data={'moogt': MoogtNotificationSerializer(self.moogt).data})
                    self.moogt.save()

                    self.state = MiniSuggestionState.APPROVED.value
                    self.save()
                    break

        if not notification_sent:
            from .serializers import MoogtMiniSuggestionNotificationSerializer
            notify.send(recipient=recipients,
                        sender=sender,
                        verb="approved suggestion",
                        send_email=False,
                        send_telegram=True,
                        type=NOTIFICATION_TYPES.mini_suggestion_action,
                        category=Notification.NOTIFICATION_CATEGORY.message,
                        target=self,
                        data={
                            'moogt': MoogtNotificationSerializer(self.moogt).data,
                            'mini_suggestion': MoogtMiniSuggestionNotificationSerializer(self).data
                        })

    def disapprove(self):
        self.state = MiniSuggestionState.DISAPPROVED.value
        self.save()

    def get_type(self):
        from .serializers import MoogtMiniSuggestionSerializer

        for field in MoogtMiniSuggestionSerializer.allowed_fields:
            if field == 'tags':
                if self.tags.count() > 0:
                    return 'tags'
            elif getattr(self, field) and getattr(self, field) is not None:
                return field

    def cancel(self):
        self.state = MiniSuggestionState.CANCEL.value
        self.save()


class MoogtStats(Stats):
    """Keeps track of stats for a moogt."""

    moogt = AutoOneToOneField(Moogt,
                              related_name="stats",
                              primary_key=True,
                              on_delete=models.CASCADE)

    view_count = models.IntegerField(default=0)

    def func_proposition_win_percent(self):
        prop_upvotes = 0
        prop_num_voters = 0
        oppo_upvotes = 0
        oppo_num_voters = 0
        for argument in self.moogt.arguments.all():
            if argument.user == self.moogt.get_proposition():
                prop_upvotes += argument.stats.upvotes.count()
                prop_num_voters += argument.stats.func_num_voters()
            else:
                oppo_upvotes += argument.stats.upvotes.count()
                oppo_num_voters += argument.stats.func_num_voters()

        prop_upvote_percent = 0
        oppo_upvote_percent = 0
        if prop_num_voters > 0:
            prop_upvote_percent = 100 * \
                float(prop_upvotes) / float(prop_num_voters)
        if oppo_num_voters > 0:
            oppo_upvote_percent = 100 * \
                float(oppo_upvotes) / float(oppo_num_voters)

        prop_win_percent = int(
            (100 + prop_upvote_percent - oppo_upvote_percent) / 2.0)

        return prop_win_percent

    def func_opposition_win_percent(self):
        return 100 - self.func_proposition_win_percent()

    def func_has_any_votes(self):
        for argument in self.moogt.arguments.all():
            if argument.stats.func_num_voters() > 0:
                return True
        return False

    def func_update_share_count(self, provider, count):
        """
        Update the share count for this moogt stats.
        :param provider: The type of the platform. e.g., facebook
        :param count: The share count for this share provider.
        :return:
        """
        moogt_stat_type = ContentType.objects.get_for_model(MoogtStats)
        super().update_share_count(provider, count, moogt_stat_type)

    def func_get_share_count(self):
        return self.get_share_count()

    def get_moogt(self):
        return self.moogt

    def set_moogt(self, value):
        self.moogt = value

    def get_view_count(self):
        return self.view_count

    def set_view_count(self, value):
        self.view_count = value


class MoogtScore(Score):
    moogt = AutoOneToOneField(Moogt,
                              related_name='score',
                              primary_key=True,
                              on_delete=models.CASCADE)

    def calculate_score(self):
        return self.moogt.calculate_score()


class MoogtGroup(models.Model):
    """"Represents a group(which is required for group moogts)"""

    # The users which belong to this group
    users = models.ManyToManyField(MoogtMedaUser, related_name='moogt_groups')


class MoogtParticipant(models.Model):
    """A class representing moogt participants either as opposition or proposition"""
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='moogt_participant',
                             null=True,
                             on_delete=models.SET_NULL)

    moogt_group = models.ForeignKey(
        MoogtGroup, related_name='+', null=True, on_delete=models.SET_NULL)


class MoogtActivityBundle(Timestampable):
    """A class representing a bundle of activities"""
    moogt = models.ForeignKey(Moogt,
                              related_name='bundles',
                              on_delete=models.SET_NULL,
                              null=True)


class MoogtActivity(AbstractActivity):
    # The linked moogt for this activity.
    moogt = models.ForeignKey(Moogt,
                              related_name='activities',
                              on_delete=models.SET_NULL,
                              null=True)

    # The bundle that this activity belongs to
    bundle = models.ForeignKey(MoogtActivityBundle,
                               related_name='activities',
                               on_delete=models.SET_NULL,
                               null=True)

    # The type of the activity, it could be an end request, a card request so on.
    type = models.CharField(choices=[(status.name, status.value) for status in MoogtActivityType],
                            default=None,
                            max_length=15,
                            null=True)

    react_to = models.ForeignKey(Argument,
                                 related_name='moogter_reaction_activities',
                                 null=True,
                                 on_delete=models.SET_NULL)

    objects = MoogtActivityManager()


class MoogtStatus(Timestampable):
    # The status a moogt is in at a particular time
    STATUS = Choices('started', 'paused', 'auto_paused', 'paused',
                     'resumed', 'broke_off', 'ended', 'duration_over')

    # The user responsible for this status.
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='+',
                             null=True,
                             on_delete=models.SET_NULL)

    # The moogt this status object belongs to
    moogt = models.ForeignKey(Moogt,
                              related_name='statuses',
                              null=True,
                              on_delete=models.SET_NULL)

    status = models.CharField(choices=STATUS, max_length=20)

    objects = MoogtStatusManager()


class Donation(Timestampable):
    """A model representing a donation to a moogt."""

    # The moogt this donation is for.
    moogt: Moogt = models.ForeignKey(Moogt,
                                     related_name='donations',
                                     null=True,
                                     on_delete=models.SET_NULL, )

    # Whether or not this donation is for the proposition.
    donation_for_proposition = models.BooleanField(null=True,
                                                   default=None)

    # The live message for the donation.
    message = models.CharField(max_length=200,
                               null=True)

    # The degree level of the donation, the higher the level the greater the donation.
    level = models.CharField(max_length=7,
                             choices=DonationLevel.all(),
                             default=DonationLevel.LEVEL_1.name)

    # The amount of the donation level.
    amount = models.IntegerField(null=True)

    # The user who made the donation.
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='+',
                             null=True,
                             on_delete=models.SET_NULL)

    # The anonymity of this donation
    is_anonymous = models.BooleanField(default=False)

    # The user who received the donation.
    donated_for = models.ForeignKey(MoogtMedaUser,
                                    related_name='donations',
                                    null=True,
                                    on_delete=models.SET_NULL)

    objects = DonationManager()

    @staticmethod
    def get_equivalence_amount(level):
        if level == DonationLevel.LEVEL_1.name:
            return 1
        if level == DonationLevel.LEVEL_2.name:
            return 5
        if level == DonationLevel.LEVEL_3.name:
            return 10
        if level == DonationLevel.LEVEL_4.name:
            return 100
        if level == DonationLevel.LEVEL_5.name:
            return 1000

    @staticmethod
    def get_equivalence_level(amount):
        if amount < 5:
            return DonationLevel.LEVEL_1.name
        elif amount < 10:
            return DonationLevel.LEVEL_2.name
        elif amount < 100:
            return DonationLevel.LEVEL_3.name
        elif amount < 1000:
            return DonationLevel.LEVEL_4.name
        else:
            return DonationLevel.LEVEL_5.name

    def save(self, *args, **kwargs):
        self.donated_for = self.moogt.proposition if self.donation_for_proposition else self.moogt.opposition
        super().save(*args, **kwargs)
        self.send_web_socket_message()

    def send_web_socket_message(self):
        channel_layer = get_channel_layer()
        from .serializers import DonationSerializer
        async_to_sync(channel_layer.group_send)(f'{self.moogt.id}', {
            'type': 'receive_group_message',
            'donation': DonationSerializer(self).data,
            'event_type': MoogtWebsocketMessageType.DONATION_MADE.name
        })


class ReadBy(Timestampable):
    # The moogt this read by belongs to
    moogt = models.ForeignKey(Moogt,
                              related_name="+",
                              null=True,
                              on_delete=models.SET_NULL)

    # The user that this read by belongs to
    user = models.ForeignKey(MoogtMedaUser,
                             related_name="read_moogts",
                             null=True,
                             on_delete=models.SET_NULL)

    # The time which the user has read the moogt before from
    latest_read_at = models.DateTimeField(default=timezone.now)


class MoogtReport(BaseReport):
    # The moogt this reported is made for.
    moogt = models.ForeignKey(
        Moogt, related_name='reports', null=False, blank=False, on_delete=models.CASCADE)

    def reported_on(self):
        return self.moogt.proposition

    def item_created_at(self):
        return self.moogt.created_at

    def __str__(self) -> str:
        return str(self.moogt)


class MoogtActivityAction(AbstractActivityAction):
    activity = models.ForeignKey(
        MoogtActivity, related_name='actions', on_delete=models.CASCADE)
