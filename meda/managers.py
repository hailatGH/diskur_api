from django.db.models import Manager

from api.models import Tag


class BaseManager(Manager):
    def create_tags(self, tags):
        created_tags = []
        for tag in tags:
            obj, created = Tag.objects.get_or_create(name=tag.get('name'))

            created_tags.append(obj)

        return created_tags

    def create(self, **kwargs):
        tags = kwargs.pop('tags') if 'tags' in kwargs else []
        obj = super().create(**kwargs)
        if tags:
            created_tags = self.create_tags(tags)
            obj.add_tags(created_tags)

        return obj
    
    def get_queryset(self):
        return super(BaseManager, self).get_queryset().filter(is_removed=False)
