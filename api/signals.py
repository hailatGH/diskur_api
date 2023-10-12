from django.dispatch import Signal, receiver

from arguments.models import Argument
from moogts.models import Moogt
from polls.models import Poll
from views.models import View

reaction_was_made = Signal()


@receiver(reaction_was_made)
def reaction_was_made_handler(sender, **kwargs):
    obj = kwargs.get('obj')
    from api.mixins import CommentMixin

    if isinstance(obj, View) or \
            isinstance(obj, Argument) or \
            isinstance(obj, Poll) or isinstance(obj, Moogt):

        obj.score.maybe_update_score()
        if sender == CommentMixin:
            obj.comment_count = obj.comment_count + 1
            obj.save()
