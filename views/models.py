from annoying.fields import AutoOneToOneField
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django_comments_xtd.models import XtdComment

from api.enums import ViewType, ReactionType
from arguments.models import Argument
from meda.models import BaseReport, Score, Stats, BaseModel
from users.models import MoogtMedaUser
from views.managers import ViewManager, ViewQuerySet
from notifications.models import Notification


class View(BaseModel):
    # The main content of the View supplied by the user.
    content = models.CharField(max_length=560, null=True)

    # The person who is creating the View.
    user = models.ForeignKey(MoogtMedaUser,
                             related_name='views',
                             null=True,
                             on_delete=models.SET_NULL)

    # If this view is hidden or not
    is_hidden = models.BooleanField(default=False)

    # If comment is enabled for a view
    is_comment_disabled = models.BooleanField(default=False)

    # The type of the view, it shows whether or not this view is an original view or a view that is
    # created as a result of a reaction.
    type = models.CharField(default=ViewType.VIEW.name, max_length=25,
                            choices=[(type.name, type.value) for type in ViewType])

    # The type of reaction if this view is a reaction view.
    reaction_type = models.CharField(max_length=25, choices=[(
        type.name, type.value) for type in ReactionType], null=True, blank=True)

    # If this view is draft
    is_draft = models.BooleanField(default=False)

    # The parent of this view if this view resulted from reacting on a view. The 'view_reactions'
    # is the reverse link that is used to get all the reactions of the parent view.
    parent_view = models.ForeignKey('self',
                                    related_name='view_reactions',
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    blank=True)

    # The parent of this view if this view resulted from reacting on an argument. The 'argument_reactions'
    # is the reverse link that is used to get all the reactions of the parent argument.
    parent_argument = models.ForeignKey(Argument,
                                        related_name='argument_reactions',
                                        on_delete=models.SET_NULL,
                                        null=True,
                                        blank=True)

    # If this view is edited
    is_edited = models.BooleanField(default=False)

    # The number of comments made to this view
    comment_count = models.IntegerField(default=0)

    # The related field for notifications
    notifications = GenericRelation(Notification,
                                    related_query_name='target_view',
                                    content_type_field='target_content_type',
                                    object_id_field='target_object_id',)

    # A custom model manager for the View model.
    objects = ViewManager.from_queryset(ViewQuerySet)()

    def __str__(self):
        if self.content == None:
            return ''
        if len(self.content) > 30:
            return f'{self.content[:30]}...'

        return self.content

    @property
    def parent(self):
        if self.parent_view and self.parent_argument:
            raise ValidationError(
                'A view cannot have both view and argument parents')

        if self.parent_view:
            return self.parent_view
        elif self.parent_argument:
            return self.parent_argument

    def add_images(self, images):
        # Here we are slicing the images list because, we want to allow a maximum of
        # 4 images for a view.
        self.images.bulk_create(
            [ViewImage(image=image, view=self) for image in images[:4]])

    def reactions_count_of_type(self, reaction_type):
        """
        Get number of reactions of a given type
        """
        return self.view_reactions.filter(reaction_type=reaction_type).count()

    def comments_count(self):
        return self.comment_count

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

    def check_is_content_creator(self, user):
        """
        This function checks whether user_id is the id of the creator of this view 
        """
        return self.user == user

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('api:views:view_detail', kwargs={'version': 'v1', 'pk': self.id})


class ViewImage(models.Model):
    #
    image = models.ImageField(blank=True)
    #
    view = models.ForeignKey(View,
                             related_name='images',
                             null=True,
                             on_delete=models.SET_NULL)


class ViewScore(Score):
    # The view associated with this score object.
    view = AutoOneToOneField(View,
                             related_name='score',
                             primary_key=True,
                             on_delete=models.CASCADE)

    def calculate_score(self):
        return self.view.calculate_score()


class ViewStats(Stats):
    # The view that is linked to this stat
    view = AutoOneToOneField(View,
                             related_name="stats",
                             primary_key=True,
                             on_delete=models.CASCADE)

    # List of users that applauded this view
    applauds = models.ManyToManyField(MoogtMedaUser, related_name="+")

    def set_view(self, value):
        self.view = value
        self.save()

    def applauds_count(self):
        return self.applauds.all().count()

    def func_update_share_count(self, provider, count):
        """
        Update the share count for this view stats.
        :param provider: The type of the platform. e.g., facebook
        :param count: The share count for this share provider.
        :return:
        """
        moogt_stat_type = ContentType.objects.get_for_model(ViewStats)
        super().update_share_count(provider, count, moogt_stat_type)

    def func_get_share_count(self):
        return self.get_share_count()

class ViewReport(BaseReport):
    # The view this report is made for.
    view = models.ForeignKey(View, related_name='reports', null=False, blank=False, on_delete=models.CASCADE)
    
    def reported_on(self):
        return self.view.user
    
    def item_created_at(self):
        return self.view.created_at
    
    def __str__(self) -> str:
        return str(self.view)
