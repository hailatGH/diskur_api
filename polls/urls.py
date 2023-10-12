from django.urls import include, re_path

from .views import (BrowsePollApiView, CreatePollApiView, DeletePollApiView, ReportPollApiView,
                    SharePoll, UpdatePollPublicityStatusView,
                    VotePollApiView, PollCommentCreateApiView,
                    ListPollCommentsApiView, PollDetailApiView)

app_name = 'polls'

urlpatterns = [
    re_path(r'^create/$', CreatePollApiView.as_view(), name="create_poll"),
    re_path(r'^all/$', BrowsePollApiView.as_view(), name="list_poll"),
    re_path(r'^comment/$', PollCommentCreateApiView.as_view(), name="comment_poll"),
    re_path(r'^vote/(?P<pk>\d+)/$', VotePollApiView.as_view(), name="vote_poll"),
    re_path(r'^detail/(?P<pk>\d+)/$', PollDetailApiView.as_view(), name='poll_detail'),
    re_path(r'^comment/all/(?P<pk>\d+)/$', ListPollCommentsApiView.as_view(), name='list_comment'),
    re_path(r'^share/(?P<pk>\d+)/$', SharePoll.as_view(), name="share_poll"),
    re_path(r'^update-publicity/$', UpdatePollPublicityStatusView.as_view(),
            name="update_poll_publicity"),
    re_path(r'^delete/(?P<pk>\d+)/$', DeletePollApiView.as_view(), name='delete_poll',),
    re_path(r'^report/(?P<pk>\d+)/$', ReportPollApiView.as_view(), name='report_poll',),
]