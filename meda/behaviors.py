from django.db import models
from django.utils import timezone

from api.models import Tag


class Timestampable(models.Model):
    """
    An abstract behavior representing timestamping a model with ``created_at`` and
    ``updated_at`` fields.

    For more info: https://blog.kevinastone.com/django-model-behaviors
    """
    created_at = models.DateTimeField(null=True, auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def modified(self):
        return True if self.updated_at else False

    def save(self, *args, **kwargs):
        if self.pk:
            self.updated_at = timezone.now()
        super(Timestampable, self).save(*args, **kwargs)


class Taggable(models.Model):
    # The list of tags for the content.
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        abstract = True

    def add_tags(self, tags):
        for t in tags:
            t, _ = Tag.objects.get_or_create(name=t['name'])
            self.tags.add(t)
