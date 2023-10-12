from PIL import Image
from avatar.conf import settings as avatar_settings
from avatar.models import Avatar
from avatar.utils import get_default_avatar_url
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.six import BytesIO
from rest_framework import status
from rest_framework.test import APITestCase

from api.tests.utility import create_user
from users.models import (MoogtMedaUser,
                          Profile)


def create_user_and_login(obj, username='testuser', password='testpassword'):
    user = create_user(username, password)
    profile = Profile()
    profile.user = user
    profile.save()
    user.profile = profile
    user.save()
    # This will bypass authentication and force the request to be treated as authenticated
    obj.client.force_login(user)
    return user


# Create your tests here.


# "borrowed" from easy_thumbnails/tests/test_processors.py
def create_image(storage, filename, size=(100, 100), image_mode='RGB', image_format='PNG'):
    """
    Generate a test image, returning the filename that it was saved as.

    If ``storage`` is ``None``, the BytesIO containing the image data
    will be passed instead.
    """
    data = BytesIO()
    Image.new(image_mode, size).save(data, image_format)
    data.seek(0)
    if not storage:
        return data
    image_file = ContentFile(data.read())
    return storage.save(filename, image_file)


class RenderPrimaryAvatarViewTests(APITestCase):
    def get(self, user):
        size = avatar_settings.AVATAR_DEFAULT_SIZE
        url = reverse('api:render_primary', kwargs={'user': user, 'size': size})
        return self.client.get(url)

    def test_user_is_not_authenticated(self):
        """
        If the user is not authenticated
        """
        response = self.get('test_user')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_default_avatar_url(self):
        """
        If avatar hasn't been set for a user, it should return the default avatar url
        """
        create_user_and_login(self)
        response = self.get('test_user')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['avatar'])

    def test_avatar_set_for_a_user(self):
        """
        If an avatar has been set for a user, it should return the url of that avatar
        """
        user = create_user_and_login(self, username='test_user')
        avatar = Avatar(user=user, primary=True)
        avatar_image = create_image(None, 'avatar.png')
        avatar_file = SimpleUploadedFile('test_avatar.png', avatar_image.getvalue())
        avatar.avatar.save(avatar_file.name, avatar_file)
        avatar.save()

        response = self.get('test_user')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['avatar'])
        self.assertNotEqual(response.data['avatar'], get_default_avatar_url())


class AddAvatarViewTests(APITestCase):
    def post(self, form_data=None):
        url = reverse('api:add_avatar')
        return self.client.post(url, form_data)

    def test_user_not_authenticated(self):
        """
        Unauthenticated user should not be able to add new avatar
        """
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_without_submitting_form_data(self):
        """
        It should return a bad request response, when user doesn't include the file in the request
        """
        create_user_and_login(self)
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_form_data(self):
        """
        If a valid file is included in the request, we must save the avatar for the user
        """
        user = create_user_and_login(self, username='test_user')

        # Set up form data
        avatar = create_image(None, 'avatar.png')
        avatar_file = SimpleUploadedFile('test_avatar.png', avatar.getvalue())
        form_data = {'avatar': avatar_file}

        response = self.post(form_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = MoogtMedaUser.objects.get(pk=user.id)
        user_avatar = user.avatar_set.first()
        self.assertIsNotNone(user_avatar)
        self.assertContains(response, 'test_avatar', status_code=status.HTTP_201_CREATED)


class AvatarChangeViewTests(APITestCase):
    def post(self, body=None):
        url = reverse('api:change_avatar')
        return self.client.post(url, body)

    def test_choice_not_included_in_request(self):
        """
        If the avatar choice is not included in the request, it should respond with bad request response
        """
        create_user_and_login(self)
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_avatar_with_the_given_choice_does_not_exist(self):
        """
        If the avatar choice is not existing, it should respond with not found response
        """
        create_user_and_login(self)
        response = self.post({'choice': 404})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_avatar_with_the_given_choice_exists(self):
        """
        If the avatar with the given choice exists, it should be the primary avatar of the user
        """
        user = create_user_and_login(self)

        avatar1 = Avatar(user=user, primary=True)
        avatar1_image = create_image(None, 'avatar1.png')
        avatar1_file = SimpleUploadedFile('test_avatar1.png', avatar1_image.getvalue())
        avatar1.avatar.save(avatar1_file.name, avatar1_file)
        avatar1.save()

        avatar2 = Avatar(user=user)
        avatar2_image = create_image(None, 'avatar2.png')
        avatar2_file = SimpleUploadedFile('test_avatar2.png', avatar2_image.getvalue())
        avatar2.avatar.save(avatar2_file.name, avatar2_file)
        avatar2.save()

        response = self.post({'choice': avatar2.id})

        # Make sure the chosen avatar is included in the response
        self.assertEqual(response.data['id'], avatar2.id)

        avatar2 = Avatar.objects.get(pk=avatar2.id)
        # Make sure the chosen avatar is set as the primary avatar
        self.assertTrue(avatar2.primary)

        avatar1 = Avatar.objects.get(pk=avatar1.id)
        # Make sure the previous avatar is not set as the primary avatar anymore
        self.assertFalse(avatar1.primary)


class DeleteAvatarView(APITestCase):
    def post(self, body=None):
        url = reverse('api:delete_avatar')
        return self.client.post(url, body)

    def test_user_is_not_authenticated(self):
        """
        Unauthenticated user should not be able to perform delete avatar operation
        """
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_avatar(self):
        """
        When given choices of avatars to delete, all of them should be deleted
        """
        user = create_user_and_login(self)
        avatar1 = Avatar(user=user)
        avatar1.save()

        avatar2 = Avatar(user=user)
        avatar2.save()

        response = self.post({'choices': [avatar2.id]})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        avatar1_exists = Avatar.objects.filter(id=avatar1.id).exists()
        avatar2_exists = Avatar.objects.filter(id=avatar2.id).exists()

        self.assertTrue(avatar1_exists)
        self.assertFalse(avatar2_exists)


