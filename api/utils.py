from django.db.models import Value, CharField
from django.urls import reverse


def get_union_queryset(*args, **kwargs):
    datetime_field = kwargs.pop('datetime_field', 'created')
    object_type_field = kwargs.pop('object_type_field', 'type')

    querysets = []
    for key, queryset in kwargs.items():
        querysets.append(
            queryset.annotate(**{
                object_type_field: Value(key, output_field=CharField())
            }).values('pk', object_type_field, datetime_field, *args)
        )

    union_qs = querysets[0].union(*querysets[1:])
    return union_qs.order_by(f'-{datetime_field}')


def inflate_referenced_objects(union_qs, **kwargs):
    datetime_field = kwargs.pop('datetime_field', 'created_at')
    object_type_field = kwargs.pop('object_type_field', 'type')
    field_to_include = kwargs.pop('field_to_include', False)

    records = []
    for row in union_qs:
        record = {
            object_type_field: row[object_type_field],
            'when': row[datetime_field],
            'pk': row['pk'],
        }
        if field_to_include:
            record[field_to_include] = row[field_to_include]

        records.append(record)

    # Now we bulk-load each object type in turn
    to_load = {}
    for record in records:
        to_load.setdefault(record[object_type_field], []).append(record['pk'])
    fetched = {}
    for key, pks in to_load.items():
        for item in kwargs[key].filter(pk__in=pks):
            fetched[(key, item.pk)] = item
    # Annotate 'records' with loaded objects
    for record in records:
        record['object'] = fetched[(record[object_type_field], record['pk'])]
    return records


def get_admin_url(instance):
    return reverse('admin:%s_%s_change' % (instance._meta.app_label, instance._meta.model_name), args=(instance.id,))
