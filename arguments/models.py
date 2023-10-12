from annoying.fields import AutoOneToOneField
from django.contrib.contenttypes.fields import ContentType, GenericRelation
from django.db import models
from django.utils import timezone
from django_comments_xtd.conf import settings
from django_comments_xtd.models import XtdComment
from model_utils.models import SoftDeletableModel

from api.enums import ReactionType
from meda.enums import ArgumentType
from meda.models import AbstractActivity, BaseReport, Score
from meda.models import AbstractActivityAction
from notifications.models import Notification
from users.models import MoogtMedaUser
from .enums import ArgumentActivityType, ArgumentReactionType
from .managers import ArgumentActivityManager, ArgumentManager, ArgumentQuerySet


class Argument(SoftDeletableModel):
    """Represents a single argument in a Moogt by a user. A Moogt is made up of
    many Arguments.
    """

    # The Moogt to which this Argument belongs.
    # If the Moogt is deleted, this argument should also be deleted.
    moogt = models.ForeignKey('moogts.Moogt',
                              related_name='arguments',
                              on_delete=models.CASCADE)

    # The user who made this arugument. If the user is deleted, this field
    # will be set to NULL. We do not want a user's deletion to CASCADE down to
    # all their arguments. This requries setting null=True.
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='arguments',
                             null=True,
                             on_delete=models.SET_NULL)

    # The argument text itself.
    # TODO: The character limit is temporary. It should be configurable in the
    # future.
    argument = models.CharField(max_length=560)

    # The type of this argument. It could be a normal argument or a concluding argument.
    type = models.CharField(default=ArgumentType.NORMAL.name,
                            max_length=50,
                            choices=[(t.name, t.value) for t in ArgumentType])

    reply_to = models.ForeignKey('self',
                                 related_name="+",
                                 null=True,
                                 on_delete=models.SET_NULL)

    # The pending edit of this Argument waiting on Approval
    modified_child = models.OneToOneField('self',
                                          related_name='modified_parent',
                                          null=True,
                                          on_delete=models.SET_NULL)

    # The parent reaction of this argument being reacted to. moogter_reactions is used for getting reactions made to
    # this argument by moogters(users involved in the moogt).
    react_to = models.ForeignKey('self',
                                 related_name='moogter_reactions',
                                 null=True,
                                 on_delete=models.SET_NULL)

    # The type of reaction of this argument
    reaction_type = models.CharField(default=None,
                                     max_length=50,
                                     null=True,
                                     choices=[(t.name, t.value) for t in ArgumentReactionType])

    # Indicates whether this is an original Argument Card or an Edited one
    is_edited = models.BooleanField(default=False)

    # The date/time when this argument was created.
    created_at = models.DateTimeField(default=timezone.now)

    # The last update time for this Argument.
    updated_at = models.DateTimeField(auto_now=True)

    # The number of comments made to this view
    comment_count = models.IntegerField(default=0)

    # This field is only for expired turns. Tracks the number of consecutive expired turns.
    consecutive_expired_turns_count = models.IntegerField(default=1)

    # The related field for notifications
    notifications = GenericRelation(Notification,
                                    related_query_name='target_argument',
                                    content_type_field='target_content_type',
                                    object_id_field='target_object_id',)

    objects = ArgumentManager.from_queryset(ArgumentQuerySet)()

    def __str__(self):
        if self.argument == None:
            return ''
        if len(self.argument) > 30:
            return f'{self.argument[:30]}...'
        return self.argument

    def get_absolute_url(self):
        return "%s#%s" % (self.moogt.get_absolute_url(), self.id)

    def get_type(self):
        return self.type

    def set_type(self, type):
        self.type = type

    def func_title(self):
        return self.argument[:50]

    def func_empty(self):
        return len(self.argument) == 0

    def get_moogt(self):
        return self.moogt

    def set_moogt(self, value):
        self.moogt = value

    def get_user(self):
        return self.user

    def set_user(self, value):
        self.user = value

    def get_argument(self):
        return self.argument

    def set_argument(self, value):
        self.argument = value

    def set_reply_to(self, value):
        self.reply_to = value

    def set_react_to(self, value):
        self.react_to = value

    def get_created_at(self):
        return self.created_at

    def set_created_at(self, value):
        self.created_at = value

    def get_updated_at(self):
        return self.updated_at

    def set_updated_at(self, value):
        self.updated_at = value

    def get_modified_parent(self):
        try:
            return self.modified_parent
        except:
            return None

    def comments_count(self):
        ctype = ContentType.objects.get_for_model(self)
        comments = XtdComment.objects.filter(content_type=ctype,
                                             object_pk=self.pk,
                                             site__pk=settings.SITE_ID,
                                             is_public=True)
        return comments.count()

    def reactions_count_of_type(self, reaction_type):
        """
        Get number of reactions of a given type
        """
        view_reactions_count = self.argument_reactions.filter(
            reaction_type=reaction_type).count()

        if reaction_type == ReactionType.ENDORSE.name:
            argument_reactions_count = self.moogter_reactions.filter(
                reaction_type=ArgumentReactionType.ENDORSEMENT.name).count()
        else:
            argument_reactions_count = self.moogter_reactions.filter(
                reaction_type=ArgumentReactionType.DISAGREEMENT.name).count()

        return view_reactions_count + argument_reactions_count

    def calculate_score(self):
        """
        This is a linear function that calculates the score for a view based on the params:
           - applauds count
           - agreements count
           - disagreements count
           - comments count
        """
        applauds_pts = self.stats.applauds_count()
        endorsements_pts = 2 * \
            self.reactions_count_of_type(ReactionType.ENDORSE.name)
        disagreements_pts = 2 * \
            self.reactions_count_of_type(ReactionType.DISAGREE.name)
        comments_pts = self.comments_count()

        return applauds_pts + endorsements_pts + disagreements_pts + comments_pts


class ArgumentActivity(AbstractActivity):
    # The Argument Card this activity is linked to
    argument = models.ForeignKey(Argument,
                                 related_name='activities',
                                 null=True,
                                 on_delete=models.SET_NULL)

    # The type of activity of this argument
    type = models.CharField(default=ArgumentActivityType.EDIT.value,
                            max_length=15,
                            choices=[(status.value, status.name) for status in ArgumentActivityType])

    objects = ArgumentActivityManager()


class ArgumentStats(models.Model):
    """Keeps track of stats for an argument."""

    argument = AutoOneToOneField(Argument,
                                 related_name="stats",
                                 primary_key=True,
                                 on_delete=models.CASCADE)

    # The + means there is no related name, there is no reverse link
    # from the MoogtMedaUser
    upvotes = models.ManyToManyField(MoogtMedaUser, related_name="+")

    downvotes = models.ManyToManyField(MoogtMedaUser, related_name="+")

    # List of users that applauded this argument
    applauds = models.ManyToManyField(MoogtMedaUser, related_name="+")

    # The number of endorsement count from unique users
    endorsement_count = models.IntegerField(default=0)

    # The number of disagreement ocunt from unique users
    disagreement_count = models.IntegerField(default=0)

    def func_num_votes(self):
        return self.upvotes.count() - self.downvotes.count()

    def func_num_voters(self):
        return self.upvotes.count() + self.downvotes.count()

    def get_argument(self):
        return self.argument

    def set_argument(self, value):
        self.argument = value

    def get_upvotes(self):
        return self.upvotes

    def set_upvotes(self, value):
        self.upvotes = value

    def get_downvotes(self):
        return self.downvotes

    def set_downvotes(self, value):
        self.downvotes = value

    def applauds_count(self):
        return self.applauds.all().count()


class ArgumentImage(models.Model):
    """An image for an argument."""

    # The argument this image is for.
    argument = models.ForeignKey(
        Argument, related_name='images', null=True, on_delete=models.SET_NULL)

    # The image itself.
    image = models.ImageField(upload_to='argument_images')


class ArgumentScore(Score):
    # The view associated with this score object.
    argument = AutoOneToOneField(Argument,
                                 related_name='score',
                                 primary_key=True,
                                 on_delete=models.CASCADE)

    def calculate_score(self):
        return self.argument.calculate_score()


class ArgumentReport(BaseReport):
    # The argument this report was made for
    argument = models.ForeignKey(
        Argument, null=False, blank=False, related_name='reports', on_delete=models.CASCADE)

    def reported_on(self):
        return self.argument.user

    def item_created_at(self):
        return self.argument.created_at

    def __str__(self) -> str:
        return str(self.argument)


class ArgumentActivityAction(AbstractActivityAction):
    activity = models.ForeignKey(
        ArgumentActivity, related_name='actions', on_delete=models.CASCADE)
