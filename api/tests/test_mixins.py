from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.mixins import ReportMixin, TrendingMixin
from api.tests.utility import create_user, create_view
from moogts.models import MoogtReport
from users.tests.factories import MoogtMedaUserFactory
from views.models import View, ViewReport
from views.tests.factories import ViewReportFactory


class TrendingMixinTests(TestCase):

    def setUp(self) -> None:
        self.user = create_user('test_username', 'test_password')

        self.view_one = create_view(self.user, 'test view 1')
        self.view_one.score.overall_score = 1
        self.view_one.score.save()

        self.view_two = create_view(self.user, 'test view 2')
        self.view_two.score.overall_score = 10
        self.view_two.score.save()

    def test_sorts_based_on_popularity(self):
        # Arrange
        mixin = TrendingMixin()

        # Act
        result = mixin.sort_queryset_by_popularity(View.objects.all())

        # Assert
        self.assertEqual(result.first().id, self.view_two.id)

class ReportMixinTests(TestCase):
    def setUp(self) -> None:
        self.created_by = MoogtMedaUserFactory.create()
        self.reported_by = MoogtMedaUserFactory.create()
        self.view_report = ViewReportFactory.create(reported_by=self.reported_by)
        self.mixin = ReportMixin()
    
    def test_validate_should_validate_the_users(self):
        """Should validate that the reported and the creator users are different."""
        self.assertRaises(ValidationError, 
                          self.mixin.validate, 
                          created_by=self.created_by, 
                          reported_by=self.created_by,
                          queryset=MoogtReport.objects.all())
        
    def test_validate_making_duplicate_request(self):
        """Should validate that the report that is being made isn't a duplicate."""
        self.assertRaises(ValidationError,
                          self.mixin.validate,
                          created_by=self.created_by,
                          reported_by=self.reported_by,
                          queryset=ViewReport.objects.all())
    