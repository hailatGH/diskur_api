import factory

from polls.models import Poll, PollOption
from users.tests.factories import MoogtMedaUserFactory

class PollOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PollOption
        
class PollFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Poll
    
    user = factory.SubFactory(MoogtMedaUserFactory)
    options = factory.SubFactory(PollOptionFactory)
    max_duration = factory.Faker('date_between_dates')
    
