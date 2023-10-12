from django.urls import re_path

from arguments.views import (CreateArgumentView, ReportArgumentApiView, UpvoteDownvoteArgumentView,
                             ArgumentReactionApiView, ApplaudArgumentApiView,
                             BrowseArgumentReactionsApiView, ArgumentCommentCreateApiView,
                             CreateEditRequestApiView, CreateDeleteRequestApiView, GetArgumentReactingUsersApiView,
                             DeleteRequestActionApiView, EditRequestActionApiView, ListConcludingArgumentsApiView,
                             ListArgumentCommentsApiView, ListArgumentsApiView, 
                             ArgumentDetailApiView, ListArgumentActivityApiView, AdjacentArgumentsListApiView, 
                             UploadArgumentImageApiView, ReadArgumentApiView)

app_name = 'arguments'

urlpatterns = [
    re_path(r'^create/$', CreateArgumentView.as_view(), name='create_argument'),
    re_path(r'^vote/(?P<pk>\d+)/$',
            UpvoteDownvoteArgumentView.as_view(), name='upvote_downvote'),
    re_path(r'^react/$', ArgumentReactionApiView.as_view(), name='react_argument'),
    re_path(r'^reaction/user/(?P<pk>\d+)/$', GetArgumentReactingUsersApiView.as_view(), name='users_reacting'),
    re_path(r'^request/edit/$', CreateEditRequestApiView.as_view(), name="request_edit"),
    re_path(r'^request/edit/action/$', EditRequestActionApiView.as_view(), name="request_edit_action"),
    re_path(r'^request/delete/$', CreateDeleteRequestApiView.as_view(), name="request_delete"),
    re_path(r'^request/delete/action/$', DeleteRequestActionApiView.as_view(), name="request_delete_action"),
    re_path(r'^read/$', ReadArgumentApiView.as_view(), name="read_argument"),
    re_path(r'^applaud/(?P<pk>\d+)/$', ApplaudArgumentApiView.as_view(),
            name='applaud_argument'),
    re_path(r'^reaction/all/(?P<pk>\d+)/$', BrowseArgumentReactionsApiView.as_view(),
            name='browse_argument_reactions'),
    re_path(r'^comment/$', ArgumentCommentCreateApiView.as_view(), name="comment_argument"),
    re_path(r'^comment/all/(?P<pk>\d+)/$', ListArgumentCommentsApiView.as_view(), name='list_comment'),
    re_path(r'^all/(?P<pk>\d+)/$', ListArgumentsApiView.as_view(), name='list_argument',),
    re_path(r'^concluding/all/(?P<pk>\d+)/$', ListConcludingArgumentsApiView.as_view(), name='list_concluding_argument'),
    re_path(r'^detail/(?P<pk>\d+)/$', ArgumentDetailApiView.as_view(), name='argument_detail'),
    re_path(r'^adjacent/(?P<pk>\d+)/$', AdjacentArgumentsListApiView.as_view(), name='adjacent_arguments_list'),
    re_path(r'^image/upload/$', UploadArgumentImageApiView.as_view(), name='upload_image'),
    re_path(r'^activity/all/(?P<pk>\d+)/$', ListArgumentActivityApiView.as_view(), name="list_activities"),
    re_path(r'^report/(?P<pk>\d+)/$', ReportArgumentApiView.as_view(), name="report_argument"),
]
