from django.http import HttpResponse
from django.shortcuts import redirect

from notifications.signals import notify


def index(request):
    """A stub index view."""
    return redirect('meda:browse')


def profile(request):
    """A stub profile page for a user. A custom profile view is required for the
    proper functioning of the allauth app.
    """
    return HttpResponse("You've reached the profile page.")


def send_notifications(sender, recipient, verb, target, send_email=True, action_object=None):
    notify.send(
        recipient=recipient,
        sender=sender,
        verb=verb,
        target=target,
        send_email=send_email,
        action_object=action_object)

