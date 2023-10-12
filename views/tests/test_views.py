import json
import os
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from api.enums import Visibility, ReactionType, ViewType
from api.models import Tag
from api.signals import reaction_was_made
from api.tests.tests import create_image, create_user_and_login
from api.tests.utility import create_user_and_login, create_view, create_user, create_comment, catch_signal, \
    create_argument, generate_photo_file, create_moogt_with_user, create_reaction_view
from moogtmeda.settings import MEDIA_ROOT
from notifications.models import NOTIFICATION_TYPES
from views.models import View, ViewReport, ViewStats, ViewImage
from views.tests.factories import ViewFactory


class CreateViewApiViewTests(APITestCase):
    def post(self, body=None, f="json"):
        url = reverse('api:views:create_view', kwargs={'version': 'v1'})
        return self.client.post(url, body, format=f)

    def test_unauthenticated(self):
        """
        Unauthenticated user should not be able to create a View
        """
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_publicity_status(self):
        """
        If an invalid publicity status is sent in the request, it should respond with bad request
        """
        create_user_and_login(self)
        response = self.post(
            {'content': 'test_content', 'publicity_status': 'invalid'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_view(self):
        """
        If the request is valid, it should create a new View
        """
        user = create_user_and_login(self)
        response = self.post({'content': 'test content',
                              'visibility': Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        view = View.objects.get(content='test content')
        self.assertEqual(view.user, user)
        self.assertEqual(view.visibility, Visibility.FOLLOWERS_ONLY.name)

    def test_create_view_with_tags(self):
        """
        If tags are provided, it should create them and associate them with the view
        """
        user = create_user_and_login(self)
        response = self.post({'content': 'test content',
                              'visibility': Visibility.FOLLOWERS_ONLY.name,
                              'tags': [{'name': 'tag1'}, {'name': 'tag2'}, {'name': 'tag3'}]})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        view = View.objects.get(content='test content')
        self.assertEqual(view.user, user)
        self.assertEqual(view.tags.count(), 3)

    def test_create_view_with_images(self):
        """
        If images are provided, it should create them and associate them with the view
        """
        user = create_user_and_login(self)

        view_image = ViewImage.objects.create()

        response = self.post({'content': 'test content',
                              'visibility': Visibility.PUBLIC.name,
                              'images': [view_image.id]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        view = View.objects.get(pk=response.data['id'])
        self.assertEqual(view.images.count(), 1)
        self.assertEqual(len(response.data['images']), 1)
        self.assertEqual(response.data['images'][0]['id'], view_image.id)

    def test_create_view_with_4_images(self):
        """
        Test successfully creating a view with multiple images
        """
        user = create_user_and_login(self)
        images = []
        for i in range(4):
            view_image = ViewImage.objects.create()
            images.append(view_image.id)

        response = self.post({'content': 'test content',
                              'visibility': Visibility.PUBLIC.name,
                              'images': images})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        view = View.objects.get(pk=response.data['id'])

        self.assertEqual(view.images.count(), 4)

    def test_create_view_with_5_images(self):
        """
        Creating a view with more than 4 images should give a failed response and
        should not create the view with those images
        """
        user = create_user_and_login(self)
        images = []
        for i in range(5):
            view_image = ViewImage.objects.create()
            images.append(view_image.id)

        response = self.post({'content': 'test content',
                              'visibility': Visibility.PUBLIC.name,
                              'images': images})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(View.objects.count(), 0)

    def test_with_identical_tags(self):
        """
        If identical tags are sent in the request, it should not save a duplicate
        """
        user = create_user_and_login(self)
        response = self.post({'content': 'test content',
                              'visibility': Visibility.FOLLOWERS_ONLY.name,
                              'tags': [{'name': 'tag'}, {'name': 'tag'}, {'name': 'tag'}]})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        view = View.objects.get(content='test content')
        self.assertEqual(view.user, user)
        self.assertEqual(view.tags.count(), 1)

        self.assertEqual(Tag.objects.all().count(), 1)

    def test_create_draft(self):
        """
        If a user supplies the right input it should save it as a draft
        """
        user = create_user_and_login(self)
        response = self.post({'content': 'test content',
                              'visibility': Visibility.PUBLIC.name,
                              'is_draft': True})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_draft'], True)

    def test_create_draft_with_tags(self):
        """
        If a user supplies draft with tags then it should create the view
        draft with tags
        """
        user = create_user_and_login(self)
        response = self.post({'content': 'test content',
                              'tags': [{'name': 'tag1'}, {'name': 'tag2'}, {'name': 'tag3'}],
                              'visibility': Visibility.PUBLIC.name,
                              'is_draft': True})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_draft'], True)

    def test_create_draft_with_images(self):
        """
        If a user supplies draft with images then it should create the view
        draft with images
        """
        user = create_user_and_login(self)
        view_image = ViewImage.objects.create()
        response = self.post({'images': [view_image.id],
                              'visibility': Visibility.PUBLIC.name,
                              'is_draft': True})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_draft'], True)

    def test_create_view_with_comment_disabled(self):
        """
        If a user created a view with is_comment_disabled as True
        comments should be turned off
        """
        user = create_user_and_login(self)
        response = self.post({'content': 'test content',
                              'visibility': Visibility.PUBLIC.name,
                              'is_comment_disabled': True})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_comment_disabled'], True)


class DeleteViewApiViewTests(APITestCase):
    def post(self, view_id):
        url = reverse('api:views:delete_view', kwargs={
            'pk': view_id, 'version': 'v1'})
        return self.client.post(url, format='json')

    def test_success(self):
        """
        If Valid view id is supplied it must delete the view
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        response = self.post(view.id)

        self.assertEqual(View.objects.count(), 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_reaction_views_as_well(self):
        """
        Should delete reaction views(without statement) when a view is deleted.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        view.view_reactions.create(content=None, user=user)
        self.post(view.id)
        self.assertEqual(View.objects.count(), 0)

    def test_no_view(self):
        """
        If a non existent view id is supplied to be deleted it must not delete
        """
        user = create_user_and_login(self)

        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated(self):
        """
        If an unauthenticated user deletes a view it must not delete
        """
        user = create_user("username", "password")
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        response = self.post(view.id)

        self.assertEqual(View.objects.count(), 1)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthorized(self):
        """
        If a user is not the owner of a view it must not delete
        """
        user = create_user("username", "password")
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        user = create_user_and_login(self)

        response = self.post(view.id)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(View.objects.count(), 1)


class EditViewApiViewTests(APITestCase):
    def post(self, body=None, f='json'):
        url = reverse('api:views:edit_view', kwargs={'version': 'v1'})
        return self.client.post(url, body, format=f)

    def test_success(self):
        """
        test successfully edit a view content
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.post({'content': 'test content', 'view_id': view.id})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], 'test content')
        self.assertEqual(view.is_edited, True)

    def test_same_content(self):
        """
        test if view content is same as the one being updated
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.post({'content': 'view content', 'view_id': view.id})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], 'view content')
        self.assertEqual(view.is_edited, False)

    def test_no_content(self):
        """
        test if view content is not provided it should respond with a bad request
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.post({'view_id': view.id})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.is_edited, False)

    def test_no_view_id(self):
        """
        test if view id is not provided
        """
        user = create_user_and_login(self)

        response = self.post({'content': "view content"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_view_doesnt_exist(self):
        """
        test if view doesn't exist
        """
        user = create_user_and_login(self)

        response = self.post({'content': 'view content', 'view_id': 1})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user(self):
        """
        test if an unauthenticated person tries to edit a view
        """
        user = create_user("username", "password")
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.post({'content': 'view content'})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(view.is_edited, False)

    def test_updated_at(self):
        """
        test if the updated at field updates when the content changes
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        updated_at = view.updated_at

        response = self.post({'content': 'test content', 'view_id': view.id})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(view.updated_at > updated_at)

    def test_edit_view_with_images(self):
        """
        test editing a view without images to contain images
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        image = create_image(None, 'image.png')
        file = SimpleUploadedFile('test_image.png', image.getvalue())

        response = self.post(
            {'images': [file, file], 'view_id': view.id}, f="multipart")
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.images.count(), 2)

    def test_edit_view_tags(self):
        """
        Should remove all tags if a user is trying to update by sending
        empty tags.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        tag = Tag(name='test tag')
        tag.save()
        view.tags.add(tag)

        response = self.post({'view_id': view.id, 'tags': []})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.tags.count(), 0)

    def test_edit_view_remove_existing_images(self):
        """
        Should remove all images if a user is trying to update by sending
        empty images.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        view_image = ViewImage(view=view)
        view_image.save()

        response = self.post(
            {'images': [], 'view_id': view.id})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.images.count(), 0)

    def test_edit_view_doesnot_remove_existing_images(self):
        """
        Should not remove any images if a user is trying update a view with images
        unless they specify to delete images
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        view_image = ViewImage(view=view)
        view_image.save()

        response = self.post({'view_id': view.id})
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.images.count(), 1)


class BrowseViewApiViewTests(APITestCase):
    def get(self, trending='false', view_only='false', reaction_view_only='false'):
        url = reverse('api:views:list_view', kwargs={
            'version': 'v1'}) + f'?trending={trending}'
        url += f'&view_only={view_only}&reaction_view_only={reaction_view_only}'
        return self.client.get(url)

    def test_no_view(self):
        """
        When no view exist, it must not have any result.
        """
        create_user_and_login(self)
        response = self.get()
        self.assertEqual(response.data.get('count'), 0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_a_view_exist(self):
        """
        If a view exists, it should be included in the response.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data['results'][0]['id'], view.pk)

    def test_two_views_exist(self):
        """
        If two views exist, they should be included in the response.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('count'), 2)

    def test_unauthenticated_user_view(self):
        """
        can get a list of views while unauthenticated.
        """
        user = create_user("username", "password")
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('count'), 1)

    # This test is failing just because our tests are using SQLite db.
    # Trying to get duration as seconds(or integers) is different depending on the database.
    # Since we're using PostgreSQL this test is commented out.
    # def test_returns_views_based_on_score(self):
    #     """
    #     If a view has more engagements compared to other views, it should appear first
    #     """
    #     user = create_user_and_login(self)
    #     view_1 = create_view(user, "view content 1", Visibility.PUBLIC.name)
    #     view_2 = create_view(user, "view content 2", Visibility.PUBLIC.name)
    #     view_2.created_at = timezone.now() - timedelta(days=30)
    #     view_2.save()
    #
    #     for i in range(5):
    #         # view signal takes care of updating the score of a view
    #         create_reaction_view(
    #             user, view_2, content=f'reaction view {i}', reaction_type=ReactionType.ENDORSE.name)
    #
    #     view_2.score.maybe_update_score()
    #     view_1.score.maybe_update_score()
    #
    #     response = self.get(trending='true')
    #     self.assertEqual(response.data.get('results')[0].get('id'), view_2.id)

    def test_result_includes_stats_for_views(self):
        """
        The stats for a view should be included in the response.
        """
        user = create_user_and_login(self)
        create_view(user, "view content", Visibility.PUBLIC.name)
        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['results'][0]['stats'])
        self.assertIsNotNone(response.data['results'][0]['stats']['endorse'])
        self.assertIsNotNone(response.data['results'][0]['stats']['disagree'])
        self.assertIsNotNone(response.data['results'][0]['stats']['applaud'])
        self.assertIsNotNone(response.data['results'][0]['stats']['comment'])

    def test_endorsement_count_is_correct(self):
        """
        The number of endorsement count should be correct in the stats response.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        reaction_view = create_view(
            user, 'reaction view', Visibility.PUBLIC.name)
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertEqual(
                    response.data['results'][i]['stats']['endorse']['count'], 1)
                self.assertTrue(
                    response.data['results'][i]['stats']['endorse']['selected'])

        reaction_view = create_view(
            user, 'reaction view 2', Visibility.PUBLIC.name)
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get()

        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertEqual(
                    response.data['results'][i]['stats']['endorse']['count'], 1)
                self.assertTrue(
                    response.data['results'][i]['stats']['endorse']['selected'])

    def test_disagreement_count_is_correct(self):
        """
        The number of disagreement count should be correct in the stats response.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        reaction_view = create_view(
            user, 'reaction view', Visibility.PUBLIC.name)
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.save()

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertEqual(
                    response.data['results'][i]['stats']['disagree']['count'], 1)
                self.assertTrue(
                    response.data['results'][i]['stats']['disagree']['selected'])

        reaction_view = create_view(
            user, 'reaction view 2', Visibility.PUBLIC.name)
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.save()

        response = self.get()

        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertEqual(
                    response.data['results'][i]['stats']['disagree']['count'], 1)
                self.assertTrue(
                    response.data['results'][i]['stats']['disagree']['selected'])

    def test_allowed_field_for_view_stats_should_be_set_properly(self):
        """
        If there is a disagreement without statement, you should be able to toggle to agree without statement. Therefore,
        the allowed field in the endorsement dictionary should be set to True.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        reaction_view = create_view(
            user, 'reaction view', Visibility.PUBLIC.name)
        reaction_view.content = None
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.save()

        response = self.get()
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertTrue(response.data['results'][i]['stats']['endorse']['allowed'])
                self.assertTrue(response.data['results'][i]['stats']['disagree']['allowed'])

        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get()
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertTrue(response.data['results'][i]['stats']['disagree']['allowed'])
                self.assertTrue(response.data['results'][i]['stats']['disagree']['allowed'])

        reaction_view.content = 'reaction view'
        reaction_view.save()

        response = self.get()
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertFalse(response.data['results'][i]['stats']['disagree']['allowed'])
                self.assertFalse(response.data['results'][i]['stats']['disagree']['allowed'])

        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.save()

        response = self.get()
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertFalse(response.data['results'][i]['stats']['disagree']['allowed'])
                self.assertFalse(response.data['results'][i]['stats']['disagree']['allowed'])

    def test_applauds_counts_is_set_properly(self):
        """
        The applauds count for a view should be set properly.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.get()
        self.assertEqual(response.data['results']
                         [0]['stats']['applaud']['count'], 0)

        view.stats.applauds.add(user)
        response = self.get()
        self.assertEqual(response.data['results']
                         [0]['stats']['applaud']['count'], 1)

    def test_after_applauding_a_view_the_selected_field_in_the_stat_should_be_true(self):
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.get()
        self.assertFalse(response.data['results']
                         [0]['stats']['applaud']['selected'])

        view.stats.applauds.add(user)
        response = self.get()
        self.assertTrue(response.data['results']
                        [0]['stats']['applaud']['selected'])

    def test_user_has_commented(self):
        """
        If a user has commented on a view then the stats object should indicate that
        """
        user = create_user_and_login(self)
        user_1 = create_user("username", "password")

        view = create_view(user, "view content", Visibility.PUBLIC.name)
        view_2 = create_view(user, "view content 2", Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['stats']['comment']['selected'], False)

        comment = create_comment(view, user, "test comment")

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][1]['stats']['comment']['selected'], True)
        self.assertEqual(response.data['results'][0]['stats']['comment']['selected'], False)

    def test_response_contains_images(self):
        """
        If a view has an image, the images must be included in the response.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        view_image = ViewImage(view=view)
        view_image.save()
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['images'][0]['id'], view_image.id)

    def test_valid_endorse_percentage_caluclate(self):
        """
        If a view has endorsements and disagreements it should calculate the percentage
        according to their sum
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        for i in range(2):
            # Endorsements
            user = create_user_and_login(self, f"username{i}")
            create_reaction_view(
                user, view, content=f'reaction view {i}', reaction_type=ReactionType.ENDORSE.name)

        for i in range(1):
            # Disagreements
            user = create_user_and_login(self, f"username{i + 2}")
            create_reaction_view(
                user, view, content=f'reaction view {i}', reaction_type=ReactionType.DISAGREE.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertEqual(
                    response.data['results'][i]['stats']['endorse']['percentage'], 67)
                self.assertEqual(response.data['results'][i]['stats']['endorse']['percentage'] +
                                 response.data['results'][i]['stats']['disagree']['percentage'], 100)

    def test_valid_disagree_percentage_caluclate(self):
        """
        If a view has endorsements and disagreements it should calculate the percentage
        according to their sum
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        for i in range(1):
            # Endorsements
            user = create_user_and_login(self, f"username{i}")
            create_reaction_view(
                user, view, content=f'reaction view {i}', reaction_type=ReactionType.ENDORSE.name)

        for i in range(2):
            # Disagreements
            user = create_user_and_login(self, f"username {i + 2}")
            create_reaction_view(
                user, view, content=f'reaction view {i}', reaction_type=ReactionType.DISAGREE.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for i in range(response.data.get('count')):
            if response.data['results'][i]['id'] == view.id:
                self.assertEqual(
                    response.data['results'][i]['stats']['disagree']['percentage'], 67)
                self.assertEqual(response.data['results'][i]['stats']['disagree']['percentage'] +
                                 response.data['results'][i]['stats']['endorse']['percentage'], 100)

    def test_no_reaction_calculate_percentage(self):
        """
        If a view has no reactions the endorse and disagree percentages should be 50 percent
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results']
                         [0]['stats']['endorse']['percentage'], 50)
        self.assertEqual(
            response.data['results'][0]['stats']['disagree']['percentage'], 50)

    def test_equal_endorse_disagree_percentage(self):
        """
        If a view has equal number of endorses and disagreements percentages should be 50 percent
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        create_reaction_view(user, view, content='reaction view 1',
                             reaction_type=ReactionType.ENDORSE.name)

        create_reaction_view(user, view, content='reaction view 2',
                             reaction_type=ReactionType.DISAGREE.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results']
                         [0]['stats']['endorse']['percentage'], 50)
        self.assertEqual(
            response.data['results'][0]['stats']['disagree']['percentage'], 50)

    def test_browse_followers_only_views(self):
        """
        If a view is a FOLLOWERS_ONLY view and logged in user follows the content creator
        it should be in the response
        """
        followee = create_user("username", "password")
        user = create_user_and_login(self)

        user.followings.add(followee)
        followee.followers.add(user)

        view = create_view(followee, "view content",
                           Visibility.FOLLOWERS_ONLY.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], view.pk)

    def test_browse_public_view_with_followers_only_parent(self):
        """
        If a view is a PUBLIC view and the parent view of the view is FOLLOWERS_ONLY
        it should indicate the parent view is private
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        view = create_view(user_1, "view content", Visibility.FOLLOWERS_ONLY.name)

        create_reaction_view(user_1, view, content='reaction view 1',
                             reaction_type=ReactionType.ENDORSE.name,
                             visibility=Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['parent']['content'], None)
        self.assertFalse(response.data['results'][0]['is_parent_visible'])

    def test_followers_only_view_by_creator(self):
        """
        If a view is PUBLIC and the parent is FOLLOWERS_ONLY and the owner is the creator,
        is_parent_visible should be True.
        """
        user = create_user_and_login(self)

        view = create_view(user, "view content", Visibility.FOLLOWERS_ONLY.name)
        create_reaction_view(user, view, content='reaction view 1',
                             reaction_type=ReactionType.ENDORSE.name,
                             visibility=Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['results'][0]['parent']['content'])
        self.assertTrue(response.data['results'][0]['is_parent_visible'])


    def test_browse_public_view_with_followers_only_parent_argument(self):
        """
        If a view is a PUBLIC view and the moogt of the parent argument of the view is FOLLOWERS_ONLY
        it should indicate the parent argument is private
        """
        user_1 = create_user("username", "password")
        user_2 = create_user("username2", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, resolution="test resolution",
                                       opposition=True,
                                       started_at_days_ago=1,
                                       visibility=Visibility.FOLLOWERS_ONLY.name)
        argument = create_argument(user_1, "test argument", moogt=moogt)

        create_reaction_view(user_2, argument, content='reaction view 1',
                             reaction_type=ReactionType.ENDORSE.name,
                             visibility=Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['parent']['argument'], None)
        self.assertFalse(response.data['results'][0]['is_parent_visible'])

    def test_browse_public_view_with_followers_only_parent_argument_but_followed(self):
        """
        If a view is a PUBLIC view and the moogt of the parent argument of the view is FOLLOWERS_ONLY
        and the logged in user follows the argument creator it should indicate the parent argument as visible
        """
        user_1 = create_user("username", "password")
        user_2 = create_user("username2", "password")
        user = create_user_and_login(self)

        moogt = create_moogt_with_user(user_1, resolution="test resolution",
                                       opposition=True,
                                       started_at_days_ago=1,
                                       visibility=Visibility.FOLLOWERS_ONLY.name)
        argument = create_argument(user_1, "test argument", moogt=moogt)

        user_1.followers.add(user)
        user.followings.add(user_1)

        create_reaction_view(user_2, argument, content='reaction view 1',
                             reaction_type=ReactionType.ENDORSE.name,
                             visibility=Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['parent']['argument'], 'test argument')
        self.assertTrue(response.data['results'][0]['is_parent_visible'])

    def test_browse_public_view_with_public_parent(self):
        """
        If a view is a PUBLIC view and the parent view of the view is FOLLOWERS_ONLY
        it should indicate the parent view is private
        """
        user_1 = create_user("username", "password")
        user = create_user_and_login(self)

        view = create_view(user_1, "view content", Visibility.PUBLIC.name)

        rxn_view = create_reaction_view(user_1, view, content='reaction view 1',
                                        reaction_type=ReactionType.ENDORSE.name,
                                        visibility=Visibility.PUBLIC.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['parent']['content'], 'view content')
        self.assertEqual(response.data['results'][0]['id'], rxn_view.pk)
        self.assertTrue(response.data['results'][0]['is_parent_visible'])

    def test_browse_followers_only_hidden_views(self):
        """
        If a view is a FOLLOWERS_ONLY view and logged in user follows the content creator
        but if the view is hidden it should not be in the response
        """
        followee = create_user("username", "password")
        user = create_user_and_login(self)

        user.followings.add(followee)
        followee.followers.add(user)

        view = create_view(followee, "view content",
                           Visibility.FOLLOWERS_ONLY.name, hidden=True)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_browse_followers_only_views_with_non_following_user(self):
        """
        If a view is a FOLLOWERS_ONLY view and logged in user doesn't follow the content
        creator it should not be in the response
        """
        followee = create_user("username", "password")
        user = create_user_and_login(self)

        view = create_view(followee, "view content",
                           Visibility.FOLLOWERS_ONLY.name)

        response = self.get()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_reaction_view_without_statement_is_not_included(self):
        """
        Reaction views without statement should not be included in the response.
        """
        user = create_user_and_login(self)
        view = View(user=user)
        view.save()
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_browse_only_views(self):
        """
        If the query param view_only is set to true, it should return only original views.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        reaction_view = create_view(
            user, 'test reaction view', Visibility.PUBLIC.name)
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.save()

        response = self.get(view_only='true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], view.id)

    def test_browse_only_reaction_views(self):
        """
        If the query param reaction_view_only is set to true, it should return only reaction views.
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        reaction_view = create_view(
            user, 'test reaction view', Visibility.PUBLIC.name)
        reaction_view.parent_view = view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.save()

        response = self.get(reaction_view_only='true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], reaction_view.id)

    def test_browse_only_reaction_views_from_arguments(self):
        """
        If the query param reaction_view_only is set to true, it should include reaction views created from arguments.
        """
        user = create_user_and_login(self)
        argument = create_argument(user, "test argument")
        rxn_view = create_reaction_view(user, argument, content=f'reaction view 1',
                                        reaction_type=ReactionType.ENDORSE.name, hidden=False)

        response = self.get(reaction_view_only='true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], rxn_view.pk)
        self.assertEqual(response.data['results'][0]['parent']['id'], argument.pk)

    def test_draft_post_should_not_be_included(self):
        """
        A draft view post should not be included in the browse response.
        """
        user = create_user('user1', 'test_password')
        view = create_view(user, 'test reaction')
        view.is_draft = True
        view.save()
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)


class UpdateViewPublicityStatusViewTest(APITestCase):
    def post(self, body):
        url = reverse('api:views:update_view_publicity',
                      kwargs={'version': 'v1'})
        return self.client.post(url, body, format="json")

    def test_successfully_update_poll(self):
        """
        Test successfully update publicity status of a view
        """

        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)
        response = self.post({"view_id": view.id,
                              "visibility": Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["visibility"], Visibility.FOLLOWERS_ONLY.name)

    def test_non_existent_moogt(self):
        """
        Test updating publicity status of a non existent view
        """
        user = create_user_and_login(self)
        response = self.post({"view_id": 1,
                              "visibility": Visibility.FOLLOWERS_ONLY.name})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_status(self):
        """
        Test Updating publicity status with an invalid status
        """
        user = create_user_and_login(self)
        view = create_view(user, "view content", Visibility.PUBLIC.name)

        response = self.post({"view_id": view.id,
                              "visibility": "Invalid status"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ApplaudViewApiViewTests(APITestCase):
    def post(self, view_id):
        url = reverse('api:views:applaud_view', kwargs={
            'version': 'v1', 'pk': view_id})
        return self.client.post(url)

    def test_applaud_a_view(self):
        """
        Test applaud to a view successfully
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        response = self.post(view.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.stats.applauds.count(), 1)
        self.assertEqual(user.notifications.count(), 0)

    def test_other_person_applauding_a_view(self):
        """
        Test applauding from non creator sends notification for creator
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)

        view = create_view(creator, "test view", Visibility.PUBLIC.name)

        response = self.post(view.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.stats.applauds.count(), 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_applaud)

    def test_applaud_a_non_existing_view(self):
        """
        test applaud to a non existing view
        """
        user = create_user_and_login(self)
        response = self.post(1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ViewStats.objects.count(), 0)

    def test_applaud_and_try_to_applaud_again(self):
        """
        If there is an applaud to a view and a user tries to applaud again, the applaud should
        be toggled. That is the registered applaud should be removed.
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)
        # Applaud
        response = self.post(view.id)
        # Applaud again
        response = self.post(view.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.stats.applauds.count(), 0)
        self.assertEqual(creator.notifications.count(), 0)

    def test_stats_are_properly_set(self):
        """
        The applauds_count field should be properly set for a view.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        # Applaud
        response = self.post(view.id)

        self.assertEqual(response.data['stats']['applaud']['count'], 1)
        response = self.post(view.id)
        self.assertEqual(response.data['stats']['applaud']['count'], 0)

    def test_stats_has_applauded_should_be_properly_set(self):
        """
        The has_applauded field must be set properly.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        # Applaud
        response = self.post(view.id)

        self.assertTrue(response.data['stats']['applaud']['selected'])
        response = self.post(view.id)
        self.assertFalse(response.data['stats']['applaud']['selected'])

    def test_should_send_reaction_was_made_signal_if_successful(self):
        """
        If the request is successful, it should send a signal.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        with catch_signal(reaction_was_made) as handler:
            self.post(view.id)

        handler.assert_called_once_with(
            sender=mock.ANY,
            obj=view,
            type=ReactionType.APPLAUD.name,
            signal=reaction_was_made
        )

    def test_should_not_send_reaction_was_made_signal_if_unsuccessful(self):
        """
        If the request is not successful, it must not send a signal.
        """
        create_user_and_login(self)

        with catch_signal(reaction_was_made) as handler:
            self.post(404)

        handler.assert_not_called()


class BrowseViewReactionsApiViewTests(APITestCase):

    def setUp(self):
        self.user = create_user_and_login(self)
        self.view = create_view(
            self.user, 'test content', Visibility.PUBLIC.name)

    def get(self, view_id, reaction_type=None, own_only='false'):
        url = reverse(
            'api:views:browse_view_reactions',
            kwargs={'version': 'v1', 'pk': view_id}
        ) + f'?type={reaction_type}&own={own_only}'
        return self.client.get(url)

    def test_unauthenticated_user(self):
        """
        An unauthenticated user should only see all reactions.
        """
        view = create_view(self.user, 'test content')
        view.parent_view = self.view
        view.type = ViewType.VIEW_REACTION.name
        view.reaction_type = ReactionType.DISAGREE.name
        view.save()

        self.client.logout()
        response = self.get(self.view.id, ReactionType.DISAGREE.name, 'true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_no_type_query_param(self):
        """
        If the type of the reaction is not provided, it should respond with a 400 response.
        """
        response = self.get(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_only_reactions_with_statement(self):
        """
        The response should only include reactions with a statement.
        """
        user1 = create_user('user1', 'test_password')
        user2 = create_user('user2', 'test_password')

        view1 = create_view(user1)
        view1.parent_view = self.view
        view1.type = ViewType.VIEW_REACTION.name
        view1.reaction_type = ReactionType.ENDORSE.name
        view1.save()

        view2 = create_view(user2, 'test content')
        view2.parent_view = self.view
        view2.type = ViewType.VIEW_REACTION.name
        view2.reaction_type = ReactionType.DISAGREE.name
        view2.save()

        response = self.get(self.view.id, ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

        response = self.get(self.view.id, ReactionType.DISAGREE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_create_two_reactions_and_try_to_get_reactions(self):
        """
        If there are two reactions, one by an authenticated user and one by other user,
        you should get all reactions by others if you try to get all the reactions of
        a given type.
        """
        view1 = create_view(self.user, 'test content1')
        view1.parent_view = self.view
        view1.type = ViewType.VIEW_REACTION.name
        view1.reaction_type = ReactionType.ENDORSE.name
        view1.save()

        user2 = create_user('user2', 'test_password')
        view2 = create_view(user2, 'test content2')
        view2.parent_view = self.view
        view2.type = ViewType.VIEW_REACTION.name
        view2.reaction_type = ReactionType.ENDORSE.name
        view2.save()

        response = self.get(self.view.id, ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['content'], 'test content2')

    def test_get_only_your_own_reactions(self):
        """
        If the own query param is set to true, then you should only get your own reactions
        """
        view1 = create_view(self.user, 'test reaction')
        view1.parent_view = self.view
        view1.type = ViewType.VIEW_REACTION.name
        view1.reaction_type = ReactionType.ENDORSE.name
        view1.save()

        user2 = create_user('user2', 'test_password')
        view2 = create_view(user2, 'test content2')
        view2.parent_view = self.view
        view2.type = ViewType.VIEW_REACTION.name
        view2.reaction_type = ReactionType.ENDORSE.name
        view2.save()

        response = self.get(self.view.id, ReactionType.ENDORSE.name, 'true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['content'], 'test reaction')

    def test_make_sure_you_are_getting_reaction_of_correct_reaction_type(self):
        """
        You should get reactions of the correct reaction type you asked for.
        """
        user1 = create_user('user1', 'test_password')
        view1 = create_view(user1, 'test reaction')
        view1.parent_view = self.view
        view1.type = ViewType.VIEW_REACTION.name
        view1.reaction_type = ReactionType.ENDORSE.name
        view1.save()

        user2 = create_user('user2', 'test_password')
        view2 = create_view(user2, 'test content2')
        view2.parent_view = self.view
        view2.type = ViewType.VIEW_REACTION.name
        view2.reaction_type = ReactionType.DISAGREE.name
        view2.save()

        response = self.get(self.view.id, ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['content'], 'test reaction')

        response = self.get(self.view.id, ReactionType.DISAGREE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results']
                         [0]['content'], 'test content2')

    def test_make_sure_hidden_endorsement_reaction_views_are_not_inlcuded(self):
        """
        If a reaction view is hidden then it should not show up in response
        """
        user1 = create_user('user1', 'test_password')
        rxn_view1 = create_reaction_view(user1, self.view, content=f'reaction view 1',
                                         reaction_type=ReactionType.ENDORSE.name, hidden=False)

        user2 = create_user('user2', 'test_password')
        rxn_view2 = create_reaction_view(user2, self.view, content=f'reaction view 2',
                                         reaction_type=ReactionType.ENDORSE.name, hidden=True)

        response = self.get(self.view.id, ReactionType.ENDORSE.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], rxn_view1.pk)

    def test_make_sure_hidden_disagreement_reaction_views_are_not_inlcuded(self):
        """
        If a reaction view is hidden then it should not show up in response
        """
        user1 = create_user('user1', 'test_password')
        rxn_view1 = create_reaction_view(user1, self.view, content=f'reaction view 1',
                                         reaction_type=ReactionType.DISAGREE.name, hidden=False)

        user2 = create_user('user2', 'test_password')
        rxn_view2 = create_reaction_view(user2, self.view, content=f'reaction view 2',
                                         reaction_type=ReactionType.DISAGREE.name, hidden=True)

        response = self.get(self.view.id, ReactionType.DISAGREE.name)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], rxn_view1.pk)


class HideViewApiViewTests(APITestCase):
    def post(self, view_id):
        url = reverse('api:views:hide_view', kwargs={
            'version': 'v1', 'pk': view_id})
        return self.client.post(url)

    def test_success(self):
        """
        Successfully hide a view
        """
        user = create_user_and_login(self)

        view = create_view(user, "test content")
        response = self.post(view.id)
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.is_hidden, True)

    def test_non_existent_view(self):
        """
        If the view doesn't exist it should not hide the view
        """
        user = create_user_and_login(self)

        response = self.post(1)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated(self):
        """
        If a user is not authenticated it should not hide the view
        """
        user = create_user("username", "password")
        view = create_view(user, "test content")
        response = self.post(view.id)
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(view.is_hidden, False)

    def test_hide_unhide_view(self):
        """
        Successfully hide a view and unhide it
        """
        user = create_user_and_login(self)
        view = create_view(user, "test content")
        response = self.post(view.id)
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.is_hidden, True)

        reponse = self.post(view.id)
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.is_hidden, False)

    def test_unauthorized(self):
        """
        If a user is not the owner of a view the user should not be able to hide the view
        """
        user = create_user("username", "password")
        view = create_view(user, "test content")
        user = create_user_and_login(self)

        response = self.post(view.id)
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(view.is_hidden, False)


class ViewReactionApiTests(APITestCase):
    def post(self, body=None, f='json', version='v1'):
        url = reverse('api:views:react_view', kwargs={'version': version})
        return self.client.post(url, body, format=f)

    def test_react_view(self):
        """
        Make a successful reaction to a view
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test content',
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(user.notifications.count(), 0)

    def test_react_view_by_non_creator(self):
        """
        Make a successful reaction to a view by a non reactor should
        send notification for the creator
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test content',
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_agree)

    def test_react_has_no_type(self):
        """
        Reaction object request has no type
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        response = self.post({'content': 'test content',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endorse_without_a_statement(self):
        """
        It should create a reaction view, if you're trying to agree with a view
        without a statement.
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content__isnull=True,
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_agree)

    def test_disagree_without_a_statement(self):
        """
        If should create a reaction view, if you're trying to disagree with a view
        without a statement.
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.DISAGREE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content__isnull=True,
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_disagree)

    def test_react_has_no_view_id(self):
        """
        test Reaction object request has no view id
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            user=user
        ).count(), 0)

    def test_react_to_non_existing_view(self):
        """
        test Reaction object reacts to a non existing view
        """
        user = create_user_and_login(self)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'view_id': 1})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            user=user
        ).count(), 0)

    def test_unauthenticated_user_react_to_view(self):
        """
        test unauthenticated user reacts to a view
        """
        user = create_user("username", "password")
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            user=user
        ).count(), 0)

    def test_endorse_without_a_statement_and_then_endorse_with_statement(self):
        """
        If you have previously agreed to a view without statement, then you try to agree with statement,
        it should update the existing agreement reaction to have your new statement.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        self.post({'type': ReactionType.ENDORSE.name,
                   'view_id': view.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse',
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 1)

    def test_disagree_without_statement_and_then_disagree_with_statement(self):
        """
        If you have previously disagreed to a view without statement, then you try to disagree with a statement,
        it should update the existing disagreement reaction to have your new statement.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        self.post({'type': ReactionType.DISAGREE.name,
                   'view_id': view.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test Endorse',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content='test Endorse',
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 1)

    def test_endorse_and_disagree(self):
        """
        test view for Endorse and then Disagree
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        self.post({'type': ReactionType.ENDORSE.name,
                   'content': 'test Endorse',
                   'view_id': view.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test disagree',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse',
            user=user
        ).count(), 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content='test disagree',
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 2)

    def test_endorse_without_a_statement_and_then_disagree_with_statement(self):
        """
        If you're trying to disagree to a view that already has an agreement reaction without statement,
        and you don't provide both agreement and disagreement statements, it should respond with bad request.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        self.post({'type': ReactionType.ENDORSE.name,
                   'view_id': view.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test disagree',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disagree_without_a_statement_and_then_agree_with_statement(self):
        """
        If you're trying to agree to a view that already has an disagreement reaction without statement,
        and you don't provide both agreement and disagreement statements, it should respond with bad request.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        self.post({'type': ReactionType.DISAGREE.name,
                   'view_id': view.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test agreement',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endorse_with_a_statement(self):
        """
        Test view for Endorse
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view ", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse',
            user=user
        ).count(), 1)

    def test_applaud_and_endorse_and_disagree(self):
        """
        test view for Applaud, Endorse and then Disagree
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        self.post({'type': ReactionType.ENDORSE.name,
                   'content': 'test Endorse',
                   'view_id': view.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'content': 'test Disagree',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse',
            user=user
        ).count(), 1)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name,
            content='test Disagree',
            user=user
        ).count(), 1)
        self.assertEqual(view.view_reactions.count(), 2)

    def test_agree_without_statement_and_then_try_to_agree_without_statement_again(self):
        """
        If you try to agree without statement to a view that already has an agreement without statement,
        it should be toggled.
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)

        self.post({'type': ReactionType.ENDORSE.name,
                   'view_id': view.id})

        self.assertEqual(creator.notifications.count(), 1)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name
        ).count(), 0)
        self.assertEqual(view.view_reactions.count(), 0)
        self.assertEqual(creator.notifications.count(), 0)

    def test_agree_without_statement_and_then_try_to_disagree_without_statement(self):
        """
        If you try to agree without statement and then try to disagree without statement
        it should toggle the agreement statement to disagreement statement
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 1)
        self.assertEqual(response.data['stats']['disagree']['count'], 0)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_agree)

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['endorse']['count'], 0)
        self.assertEqual(response.data['stats']['disagree']['count'], 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_disagree)

    def test_disagree_without_statement_and_then_try_to_disagree_without_statement_again(self):
        """
        If you try to agree without statement to a view that already has an agreement without statement,
        it should be toggled.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        self.post({'type': ReactionType.DISAGREE.name,
                   'view_id': view.id})

        response = self.post({'type': ReactionType.DISAGREE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.DISAGREE.name
        ).count(), 0)
        self.assertEqual(view.view_reactions.count(), 0)

    def test_endorse_and_endorse(self):
        """
        test view Applaud and double Endorse
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse',
                              'view_id': view.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            content='test Endorse'
        ).count(), 2)
        self.assertEqual(view.view_reactions.count(), 2)

    def test_view_reaction_setting_privacy_on_creation(self):
        """
        test reaction view privacy setting on creation of the reaction view
        """

        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test Endorse',
                              'visibility': Visibility.FOLLOWERS_ONLY.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(
            type=ViewType.VIEW_REACTION.name,
            reaction_type=ReactionType.ENDORSE.name,
            visibility=Visibility.FOLLOWERS_ONLY.name,
            content='test Endorse'
        ).count(), 1)

    def test_endorse_with_image(self):
        """
        test view endorse with image successfully
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        images = []
        for i in range(2):
            images.append(ViewImage.objects.create().id)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test endorse",
                              'view_id': view.id,
                              'images': images})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(view.view_reactions.first().images.count(), 2)

    def test_endorse_with_image_and_tags(self):
        """
        test view endorse with images and tags successfully
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        images = []
        for i in range(2):
            images.append(ViewImage.objects.create().id)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test endorse",
                              'view_id': view.id,
                              'images': images,
                              'tags': [{'name': 'tag1'}, {'name': 'tag2'}, {'name': 'tag3'}]})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(view.view_reactions.first().tags.count(), 3)
        self.assertEqual(view.view_reactions.first().images.count(), 2)

    def test_endorse_with_tags(self):
        """
        test view endorse tags successfully
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test endorse",
                              'view_id': view.id,
                              '[tags]': json.dumps([{'name': 'tag1'}, {'name': 'tag2'}, {'name': 'tag3'}])},
                             f='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(view.view_reactions.first().tags.count(), 3)

    def test_endorse_with_tags_json(self):
        """
        test view endorse tags with json format
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test endorse",
                              'view_id': view.id,
                              '[tags]': json.dumps([{'name': 'tag1'}, {'name': 'tag2'}, {'name': 'tag3'}])},
                             f='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(view.view_reactions.first().tags.count(), 3)

    def test_endorsing_hidden_view(self):
        """
        test endorsing a hidden view should fail
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view",
                           Visibility.PUBLIC.name, hidden=True)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test endorse",
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(view.view_reactions.count(), 0)

    def test_react_view_with_comment_not_provided(self):
        """
        test view if is_comment_disabled is not provided comment
        should be enabled
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test endorse',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(
            view.view_reactions.first().is_comment_disabled, False)

    def test_react_view_with_disabled_comment(self):
        """
        test view endorse with commenting disabled
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test endorse',
                              'view_id': view.id,
                              'is_comment_disabled': True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 1)
        self.assertEqual(
            view.view_reactions.first().is_comment_disabled, True)

    def test_agree_on_a_view_with_agreement_with_statement(self):
        """
        If a user tries to agree on a view with agreement with statement it
        respond as disabled and not create an empty view with no content
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test endorse',
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['stats']
                        ['endorse']['has_reaction_with_statement'])

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(view.view_reactions.count(), 1)

    def test_sends_a_signal_if_successful(self):
        """
        If successful it should send a signal.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        with catch_signal(reaction_was_made) as handler:
            self.post({'type': ReactionType.ENDORSE.name,
                       'content': 'test endorse',
                       'view_id': view.id})

        handler.assert_called_once_with(
            sender=mock.ANY,
            obj=view,
            type=ReactionType.ENDORSE.name,
            signal=reaction_was_made
        )

    def test_endorse_with_one_user_and_endorse_with_another_user(self):
        """
        If a user endorses a view without statement and another user endorses the same
        view without statement it should not delete the first users endorsement reaction
        """
        user = create_user_and_login(self)
        view = create_view(user, 'test view', Visibility.PUBLIC.name)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        user_1 = create_user_and_login(self, 'test_username', 'password')
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 2)

    def test_endorse_without_statement_and_endorse_without_statement(self):
        """
        If a user endorses a view without statement and endorse again on that view
        it should remove the first endorsement reaction
        """
        user = create_user_and_login(self)
        view = create_view(user, 'test view', Visibility.PUBLIC.name)

        user_1 = create_user_and_login(self, 'test_username', 'password')
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'view_id': view.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(view.view_reactions.count(), 0)

    def test_version_2_api(self):
        """
        In version 2 of the api we should return the newly reacted object and
        also should expand the parent.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)
        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': 'test content',
                              'view_id': view.id},
                             version='v2')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['parent']['id'], view.id)

    def test_endorse_with_image_version_2(self):
        """
        should return view images after making a reaction.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        images = []
        for i in range(2):
            images.append(ViewImage.objects.create().id)

        response = self.post({'type': ReactionType.ENDORSE.name,
                              'content': "test endorse",
                              'view_id': view.id,
                              'images': images}, version='v2')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['images']), 2)
        self.assertEqual(response.data['images'][0]['id'], images[0])
        self.assertEqual(response.data['images'][1]['id'], images[1])


class UploadViewImageApiViewTests(APITestCase):
    def tearDown(self) -> None:
        if os.path.exists(MEDIA_ROOT):
            for filename in os.listdir(MEDIA_ROOT):
                file_path = os.path.join(MEDIA_ROOT, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except:
                    pass

    def post(self, body=None):
        url = reverse('api:views:upload_image', kwargs={'version': 'v1'})
        return self.client.post(url, body)

    def setUp(self) -> None:
        self.user = create_user_and_login(self)

    def test_non_authenticated_user(self):
        """
        A non authenticated user should not be able to make an upload request.
        """
        self.client.logout()
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_an_image(self):
        """Upload an image to the endpoint."""
        image = generate_photo_file()
        response = self.post({'image': image})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ViewImage.objects.count(), 1)


class ViewCommentCreateAPITests(APITestCase):
    def post(self, body=None):
        url = reverse('api:views:comment_view', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_successfully_comment_on_view(self):
        """
        Test if you can successfully comment on view
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        response = self.post({
            'view_id': view.id,
            'comment': 'test comment'
        })
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(view.comments_count(), 1)
        self.assertEqual(user.notifications.count(), 0)

    def test_successfully_send_notification_for_comment(self):
        """
        Test if a non creator of a view makes comments notification is
        sent for the creator
        """
        creator = create_user("username", "password")
        user = create_user_and_login(self)
        view = create_view(creator, "test view", Visibility.PUBLIC.name)

        response = self.post({
            'view_id': view.id,
            'comment': 'test comment'
        })
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(view.comments_count(), 1)
        self.assertEqual(creator.notifications.count(), 1)
        self.assertEqual(creator.notifications.first().type, NOTIFICATION_TYPES.view_comment)

    def test_reply_to_comment(self):
        """
        Test if you can successfully reply to a comment on a view.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        comment = create_comment(view, user, "test comment")

        response = self.post({
            'view_id': view.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(view.comments_count(), 2)

    def test_comment_disabled(self):
        """
        Test commenting if view comment is disabled
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view",
                           Visibility.PUBLIC.name, comment_disabled=True)

        response = self.post({
            'view_id': view.id,
            'comment': 'test comment'
        })
        view.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(view.comments_count(), 0)

    def test_sends_a_signal_if_successful(self):
        """
        If the request is successful, it should send a signal.
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        with catch_signal(reaction_was_made) as handler:
            self.post({
                'view_id': view.id,
                'comment': 'test comment'
            })

        handler.assert_called_once_with(
            sender=mock.ANY,
            obj=view,
            signal=reaction_was_made
        )


class ListViewCommentsAPITests(APITestCase):
    def get(self, view_id, limit=3, offset=0):
        url = reverse('api:views:list_comment', kwargs={'version': 'v1', 'pk': view_id}) + '?limit=' + str(
            limit) + '&offset=' + str(offset)
        return self.client.get(url, format='json')

    def reply(self, body=None):
        url = reverse('api:views:comment_view', kwargs={'version': 'v1'})
        return self.client.post(url, body, format='json')

    def test_successfully_list_comments(self):
        """
        Test if you can successfully list all comments of a view
        """
        user = create_user_and_login(self)

        view = create_view(user, "test view", Visibility.PUBLIC.name)

        for i in range(5):
            self.reply({
                'view_id': view.id,
                'comment': 'test reply'
            })

        response = self.get(view.id, limit=5)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 5)
        for i in range(5):
            self.assertEqual(response.data['results'][i]['thread_id'], view.id)

    def test_reply_to_comment(self):
        """
        Test if you can successfully list replies to comment on a view
        """
        user = create_user_and_login(self)
        view = create_view(user, "test view", Visibility.PUBLIC.name)

        comment = create_comment(view, user, "test comment")

        self.reply({
            'view_id': view.id,
            'reply_to': comment.id,
            'comment': 'test reply'
        })

        response = self.get(view.id, limit=5)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['thread_id'], view.id)
        self.assertEqual(response.data['results'][1]['thread_id'], view.id)


class ViewDetailApiViewTests(APITestCase):
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.view = create_view(self.user, 'test view')

    def get(self, pk):
        url = reverse('api:views:view_detail', kwargs={
            'version': 'v1', 'pk': pk})
        return self.client.get(url)

    def test_get_view_detail_should_return_detailed_view_response(self):
        """
        For a given view, the endpoint should return a detailed response.
        """
        response = self.get(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], self.view.content)
        self.assertEqual(response.data['user_id'], self.user.id)

    def test_non_existing_view(self):
        """
        If the view doesn't exist, it should respond with a not found response.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_response_contains_tags(self):
        """
        The response must contain tags.
        """
        tag = Tag(name='test tag')
        tag.save()
        self.view.tags.add(tag)
        self.client.logout()

        response = self.get(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tags'][0]['name'], 'test tag')

    def test_response_contains_images(self):
        """
        The response must images, if the view has images.
        """
        view_image = ViewImage(view=self.view)
        view_image.save()

        response = self.get(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['images']), 0)

    def test_parent_view_is_deleted(self):
        """
        The response of a reaction view detail page where the parent is deleted should
        make the parent field null
        """
        rxn_view = create_reaction_view(self.user, self.view, content="reaction view")
        self.view.delete()

        response = self.get(rxn_view.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['parent'], None)

    def test_parent_argument_is_deleted(self):
        """
        The response of a reaction view detail page where the parent argument is deleted
        should make the parent field null
        """
        argument = create_argument(self.user, "test argument")
        rxn_view = create_reaction_view(self.user, argument, content="reaction view")
        argument.delete()

        response = self.get(rxn_view.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['parent'], None)

    def test_allowed_field_for_reaction_set_properly(self):
        """
        If some user has reacted without statement on a view and logged in user
        has no opposing reaction without statement it should return the allowed
        field as true
        """
        rxn_view = create_reaction_view(self.user, self.view, reaction_type=ReactionType.ENDORSE.name)
        user = create_user_and_login(self, 'test_username')

        response = self.get(self.view.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['disagree']['allowed'], True)

    def test_allowed_field_for_agreement_and_disagreement_set_properly(self):
        """
        If some user has endorsed and disagreed with statement on a view and 
        logged in user has no reactions on the view it allow field should be true
        for that view
        """
        rxn_view = create_reaction_view(self.user, self.view, content="endorsement",
                                        reaction_type=ReactionType.ENDORSE.name)
        rxn_view = create_reaction_view(self.user, self.view, content="disagreement",
                                        reaction_type=ReactionType.ENDORSE.name)

        user = create_user_and_login(self, 'test_username')

        response = self.get(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['disagree']['allowed'], True)


class GetUsersReactingApiViewTests(APITestCase):

    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.view = create_view(self.user, 'test view')

    def get(self, pk, reaction_type=None):
        url = reverse('api:views:users_reacting',
                      kwargs={'version': 'v1', 'pk': pk})
        if reaction_type:
            url += f'?type={reaction_type}'
        return self.client.get(url)

    def test_view_that_does_not_exist(self):
        """
        You should get a not found response for a view that doesn't exist.
        """
        response = self.get(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_users_who_applauded_the_view(self):
        """
        You should get the users who applauded the view, if it has applaud reactions.
        """
        user = create_user('reaction_user', 'test_password')
        self.view.stats.applauds.add(user)
        response = self.get(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_get_users_who_endorsed_the_view(self):
        """
        You should get the users who endorsed the view, if it has endorse reactions.
        """
        user = create_user('reaction_user', 'test_password')
        reaction_view = create_view(user, 'test reaction')
        reaction_view.parent_view = self.view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.ENDORSE.name
        reaction_view.save()

        response = self.get(
            self.view.id, reaction_type=ReactionType.ENDORSE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_get_users_who_disagreed_the_view(self):
        """
        You should get the users who disagreed with the view, if it has disagree reactions.
        """
        user = create_user('reaction_user', 'test_password')
        reaction_view = create_view(user, 'test reaction')
        reaction_view.parent_view = self.view
        reaction_view.type = ViewType.VIEW_REACTION.name
        reaction_view.reaction_type = ReactionType.DISAGREE.name
        reaction_view.save()

        response = self.get(
            self.view.id, reaction_type=ReactionType.DISAGREE.name)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], user.id)

    def test_invalid_type_query_parameter(self):
        """
        If the type query param is invalid, it should respond with a bad request response.
        """
        response = self.get(self.view.id, reaction_type='invalid')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_is_sorted_based_on_followers_count(self):
        """
        The list of users that is going to be returned should be sorted based on followers count.
        """
        user_1 = create_user('user_1', 'test_password')
        user_2 = create_user('user_2', 'test_password')

        follower = create_user('follower', 'test_password')
        user_2.follower.add(follower)

        self.view.stats.applauds.add(user_1)
        self.view.stats.applauds.add(user_2)

        response = self.get(self.view.id)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], user_2.id)

    def test_users_who_you_are_following_should_be_ranked_first(self):
        """
        The people that you're following should be ranked highest in the response.
        """
        user_1 = create_user('user_1', 'test_password')
        follower_user = create_user('follower_user', 'test_password')
        user_1.follower.add(follower_user)
        user_2 = create_user('user_2', 'test_password')
        user_2.follower.add(self.user)

        self.view.stats.applauds.add(user_1)
        self.view.stats.applauds.add(user_2)

        response = self.get(self.view.id)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], user_2.id)


class DeleteAllViewApiViewTests(APITestCase):
    def post(self):
        url = reverse('api:views:delete_all_view', kwargs={'version': 'v1'})
        return self.client.post(url, format='json')

    def test_success(self):
        """
        Test successfully delete all views
        """
        user = create_user_and_login(self)
        for i in range(5):
            view = create_view(user, "test content")

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.count(), 0)

    def test_unauthenticated_user(self):
        """
        Test deleting all view by an unauthenticated user must fail
        """
        user = create_user("username", "password")
        for i in range(5):
            view = create_view(user, "test content")

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(View.objects.count(), 5)

    def test_no_view_exist(self):
        """
        Test deleting all views with out any owned views should return a sucesss response
        """
        user1 = create_user("username", "password")
        for i in range(5):
            view = create_view(user1, "test content")

        user = create_user_and_login(self)
        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(View.objects.filter(user=user).count(), 0)

    def test_deleting_not_owned_views(self):
        """
        Test deleting all views with out deleting other peoples views
        """
        user1 = create_user("username", "password")
        for i in range(5):
            view = create_view(user1, "test content")

        user = create_user_and_login(self)
        for i in range(5):
            view = create_view(user, "test content")

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(user=user1).count(), 5)
        self.assertEqual(View.objects.filter(user=user).count(), 0)

    def test_deleting_a_view_with_reaction_views_from_other_users(self):
        """
        Test deleting all views with out deleting other users reaction views
        """
        user1 = create_user_and_login(self)
        view = create_view(user1, "test content")

        user2 = create_user("username1", "password")
        rxn_view = create_reaction_view(user2, view, "reaction view")

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(View.objects.filter(user=user1).count(), 0)
        self.assertEqual(View.objects.filter(user=user2).count(), 1)
        
class ViewReportApiViewTests(APITestCase):
    def post(self, view_id, data=None):
        url = reverse('api:views:report_view', kwargs={'pk': view_id, 'version': 'v1'})
        return self.client.post(url, data)
    
    def setUp(self) -> None:
        self.user = create_user_and_login(self)
        self.view = ViewFactory.create()
            
    def test_non_authenticated_user_trying_to_report_a_view(self):
        """Should get a non-authorized response."""
        self.client.logout()
        response = self.post(self.view.id)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
    def test_view_that_does_not_exist(self):
        """Should respond with a not-found response."""
        response = self.post(404)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
    @mock.patch('api.mixins.ReportMixin.validate') 
    def test_validate_request(self, mock_validate: mock.MagicMock):
        """Should validate request before creating a report."""
        self.post(self.view.id)
        mock_validate.assert_called_once_with(created_by=self.view.user, reported_by=self.user, queryset=mock.ANY)
    
    @mock.patch('api.mixins.ReportMixin.notify_admins')
    def test_notify_admins(self, mock_validate: mock.MagicMock):
        """Should notify admins."""
        self.post(self.view.id, {'link': 'https://moogter.link', 'reason': 'test reason'})
        mock_validate.assert_called_once()
        
    def test_should_create_a_view_report(self):
        """Should create a report if request is valid."""
        response = self.post(self.view.id, {'link': 'https://moogter.link', 'reason': 'test reason'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        view_reports = ViewReport.objects.all()
        self.assertEqual(view_reports.count(), 1)
        self.assertEqual(view_reports.first().view, self.view)
        self.assertEqual(view_reports.first().reported_by, self.user)
        
