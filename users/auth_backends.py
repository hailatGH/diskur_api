from allauth.account.auth_backends import AuthenticationBackend


class CustomAuthenticationBackend(AuthenticationBackend):
    """
    This Authentication backend is used to authenticate users with
    is_active set to False. All auth's AuthenticationBackend is not allowing to
    authenticate such users. We just override the user_can_authenticate func to allow
    such users to be authenticated.
    """

    def user_can_authenticate(self, user):
        return True
