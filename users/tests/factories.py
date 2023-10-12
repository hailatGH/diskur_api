import factory

from users.models import Blocking, MoogtMedaUser


class MoogtMedaUserFactory(factory.django.DjangoModelFactory):
    username = factory.Sequence(lambda n: 'user%d' % n)

    class Meta:
        model = MoogtMedaUser
        
class BlockingFactory(factory.django.DjangoModelFactory):
    
    class Meta:
        model = Blocking
        
    user = factory.SubFactory(MoogtMedaUserFactory)
    blocked_user = factory.SubFactory(MoogtMedaUserFactory)
