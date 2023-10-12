import factory

from users.tests.factories import MoogtMedaUserFactory
from views.models import View, ViewReport


class ViewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = View

    content = factory.Sequence(lambda n: 'view%d' % n)
    user = factory.SubFactory(MoogtMedaUserFactory)
    parent_view = None


class ViewReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ViewReport
        
    view = factory.SubFactory(ViewFactory)
    
    reported_by = factory.SubFactory(MoogtMedaUserFactory)
