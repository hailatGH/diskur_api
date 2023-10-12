import factory

from moogts.models import Moogt
from users.tests.factories import MoogtMedaUserFactory


class MoogtFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Moogt
        
    started_at = factory.Faker('date_object')
    proposition = factory.SubFactory(MoogtMedaUserFactory)
    opposition = factory.SubFactory(MoogtMedaUserFactory)
    moderator = factory.SubFactory(MoogtMedaUserFactory)
