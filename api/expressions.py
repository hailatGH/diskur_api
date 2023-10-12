from django.db.models import Func, IntegerField


class Epoch(Func):
    template = 'EXTRACT(epoch FROM %(expressions)s)::INTEGER'
    output_field = IntegerField()
