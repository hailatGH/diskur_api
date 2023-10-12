from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class MoogtMedaAccountAdapter(DefaultAccountAdapter):

    def get_login_redirect_url(self, request):
        return reverse('meda:browse')
