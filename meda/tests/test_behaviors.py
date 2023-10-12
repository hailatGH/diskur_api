from django.test import TestCase

from api.models import Tag
from meda.models import TimestampableMock, TaggableMock


class TestTimestamped(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mock = TimestampableMock.objects.create()

    def setUp(self):
        self.mock.refresh_from_db()

    def test_timestamp_modified_initially_false(self):
        self.assertFalse(self.mock.modified)

    def test_timestamp_modified_after_save(self):
        self.mock.save()
        self.assertTrue(self.mock.modified)


class TestTaggable(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mock = TaggableMock.objects.create()

    def test_tags_is_initially_empty(self):
        self.assertIsNotNone(self.mock.tags)
        self.assertEqual(self.mock.tags.count(), 0)

    def test_add_tags_adds_a_new_tag(self):
        tags = [{'name': 'test_tag 1'}, {'name': 'test_tag 2'}]
        self.mock.add_tags(tags)
        self.assertEqual(self.mock.tags.count(), 2)
