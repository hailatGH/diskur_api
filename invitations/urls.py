from django.urls import re_path

from invitations.views import (InviteMoogterView, UpdateInvitationView,
                               PendingInvitationListView, RecentlyInvitedUsersApiView,
                               EditInvitationView, StartInvitationView)
from invitations.views import ModeratorInvitationActionAPIView

app_name = 'invitations'

urlpatterns = [
    re_path(r'^create/$', InviteMoogterView.as_view(), name='invite_moogter'),
    re_path(r'^update/(?P<pk>\d+)/$',
            UpdateInvitationView.as_view(), name='update_invitation'),
    re_path(r'^start/(?P<pk>\d+)/$', StartInvitationView.as_view(),
            name='start_invitation'),
    re_path(r'^edit/(?P<pk>\d+)/$', EditInvitationView.as_view(),
            name='edit_invitation'),
    re_path(r'^all/$', PendingInvitationListView.as_view(),
            name="list_invitation"),
    re_path(r'^recent/$', RecentlyInvitedUsersApiView.as_view(),
            name="recent_invitation"),
    re_path(r'^moderator-action/(?P<pk>\d+)/$', ModeratorInvitationActionAPIView.as_view(),
            name="moderator_invitation_action")

]
