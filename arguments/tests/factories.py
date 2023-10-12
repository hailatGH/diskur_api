import factory

from arguments.models import Argument, ArgumentReport
from moogts.tests.factories import MoogtFactory
from users.tests.factories import MoogtMedaUserFactory


class ArgumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Argument

    user = factory.SubFactory(MoogtMedaUserFactory)
    moogt = factory.SubFactory(MoogtFactory)


class ArgumentReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ArgumentReport

    argument = factory.SubFactory(ArgumentFactory)
