from allauth.account.forms import SignupForm
from .models import Profile


class MoogtMedaSignupForm(SignupForm):
    """A custom user creation form for MoogtMeda."""

    def save(self, request):
        user = super(MoogtMedaSignupForm, self).save(request)
        # Create an associated new profile for the user.
        new_profile = Profile()
        new_profile.user = user
        new_profile.save()
        return user
