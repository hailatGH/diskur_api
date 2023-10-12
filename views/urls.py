from django.urls import re_path

from views.views import (CreateViewApiView, EditViewApiView,
                         BrowseViewApiView, ViewReactionApiView,
                         ViewDetailApiView, ShareView,
                         UpdateViewPublicityStatusView,
                         DeleteViewApiView, DeleteAllViewApiView, ApplaudViewApiView,
                         BrowseViewReactionsApiView, HideViewApiView,
                         ViewCommentCreateApiView, ListViewCommentsApiView,
                         GetUsersReactingApiView, UploadViewImageApiView, ViewReportApiView)

app_name = 'views'

urlpatterns = [
    re_path(r'^create/$', CreateViewApiView.as_view(), name='create_view'),
    re_path(r'^edit/$', EditViewApiView.as_view(), name='edit_view'),
    re_path(r'^all/$', BrowseViewApiView.as_view(), name="list_view"),
    re_path(r'^react/$', ViewReactionApiView.as_view(), name="react_view"),
    re_path(r'^detail/(?P<pk>\d+)/$', ViewDetailApiView.as_view(), name='view_detail'),
    re_path(r'^report/(?P<pk>\d+)/$', ViewReportApiView.as_view(), name='report_view'),
    re_path(r'^share/(?P<pk>\d+)/$', ShareView.as_view(), name='share_view'),
    re_path(r'^update-publicity/$', UpdateViewPublicityStatusView.as_view(),
            name="update_view_publicity"),
    re_path(r'^delete/(?P<pk>\d+)/$', DeleteViewApiView.as_view(), name='delete_view'),
    re_path(r'^delete/all/$', DeleteAllViewApiView.as_view(), name='delete_all_view'),
    re_path(r'^applaud/(?P<pk>\d+)/$', ApplaudViewApiView.as_view(), name='applaud_view'),
    re_path(r'^reaction/all/(?P<pk>\d+)/$', BrowseViewReactionsApiView.as_view(),
            name='browse_view_reactions'),
    re_path(r'^reaction/user/(?P<pk>\d+)/$', GetUsersReactingApiView.as_view(), name='users_reacting'),
    re_path(r'^hide/(?P<pk>\d+)/$', HideViewApiView.as_view(), name='hide_view'),
    re_path(r'^image/upload/$', UploadViewImageApiView.as_view(), name='upload_image'),
    re_path(r'^comment/$', ViewCommentCreateApiView.as_view(), name="comment_view"),
    re_path(r'^comment/all/(?P<pk>\d+)/$', ListViewCommentsApiView.as_view(), name='list_comment'),
]
