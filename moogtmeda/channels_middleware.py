from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from rest_framework import exceptions
from rest_framework_jwt.settings import api_settings

jwt_decode_handler = api_settings.JWT_DECODE_HANDLER
jwt_get_username_from_payload = api_settings.JWT_PAYLOAD_GET_USERNAME_HANDLER

User = get_user_model()


def authenticate_credentials(payload):
    """
    Returns an active user that matches the payload's user id and email.
    """
    username = jwt_get_username_from_payload(payload)

    if not username:
        raise exceptions.AuthenticationFailed('Invalid payload.')

    try:
        user = User.objects.get_by_natural_key(username)
    except User.DoesNotExist:
        raise exceptions.AuthenticationFailed('Invalid signature.')

    if not user.is_active:
        raise exceptions.AuthenticationFailed('User account is disabled.')

    return user


class TokenAuthMiddleware:
    """
    Custom JWT Auth Middleware for channels.
    """

    def __init__(self, inner):
        # Store the ASGI application we were passed
        self.inner = inner

    def __call__(self, scope):
        # Close old database connections to prevent usage of timed out connections
        close_old_connections()

        # Get the token
        query_string = parse_qs(scope['query_string'].decode())
        token = query_string.get('token')

        if not token:
            return self.inner(dict(scope, user=AnonymousUser()))

        # Try to authenticate the user
        try:
            payload = jwt_decode_handler(token[0])
        except Exception:
            return self.inner(dict(scope, user=AnonymousUser()))

        user = authenticate_credentials(payload)

        # Return the inner application directly and let it run everything else
        return self.inner(dict(scope, user=user))
