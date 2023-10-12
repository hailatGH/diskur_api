from django.urls import include, re_path
from fcm_django.api.rest_framework import FCMDeviceAuthorizedViewSet
from rest_framework import routers
from rest_framework_jwt.views import obtain_jwt_token, refresh_jwt_token

from .views import (AddAvatarView, AvatarListView, ChangeAvatarView, DeleteAvatarView, FeedContentApiView,
                    GetPublicityStatusView, PreferencesViewSet,
                    RenderPrimaryAvatarView, SideBarApiView,
                    ReplyCommentApiView,
                    LikeCommentApiView, UnlikeCommentApiView,
                    BrowseCommentReplyApiView, RemoveCommentApiView, SearchResultsApiView,
                    TelegramOptInApiView, SearchResultsCountApiView, CommentDetailApiView, GoogleLogin,
                    obtain_token_from_firebase_token)

app_name = 'api'

preferences_router = routers.SimpleRouter()
preferences_router.register(r'user', PreferencesViewSet, basename='user') 


router = routers.DefaultRouter()
router.register('devices', FCMDeviceAuthorizedViewSet)

urlpatterns = [
    re_path(r'^avatar/render_primary/(?P<user>[\w\d\@\.\-_]+)/(?P<size>[\d]+)/$',
            RenderPrimaryAvatarView.as_view(), name='render_primary'),
    re_path(r'^avatar/add/$', AddAvatarView.as_view(), name='add_avatar'),
    re_path(r'^avatar/all/$', AvatarListView.as_view(), name='all_avatars'),
    re_path(r'^avatar/change/$', ChangeAvatarView.as_view(),
            name='change_avatar'),
    re_path(r'^avatar/delete/$', DeleteAvatarView.as_view(),
            name='delete_avatar'), 

    re_path(r'^preferences/', include(preferences_router.urls)),

    re_path(r'^auth/token/$', obtain_jwt_token),
    re_path(r'^auth/refresh-token/$', refresh_jwt_token),
    re_path(r'^auth/firebase-token/$', obtain_token_from_firebase_token),
    
    re_path(r'^rest-auth/registration/', include('dj_rest_auth.registration.urls')),
    
    re_path(r'^rest-auth/', include('dj_rest_auth.urls')),
    re_path(r'^rest-auth/google/$', GoogleLogin.as_view(), name='google_login'),

    re_path(r'^moogter_bot/', include('moogter_bot.urls')),

    re_path(r'^fcm-django/', include(router.urls)),

    re_path(r'^(?P<version>(v1))/moogt/', include('moogts.urls')),
    re_path(r'^(?P<version>(v1))/invitation/', include('invitations.urls')),
    re_path(r'^(?P<version>(v1|v2))/argument/', include('arguments.urls')),
    re_path(r'^(?P<version>(v1))/user/', include('users.urls')),
    re_path(r'^(?P<version>(v1))/poll/', include('polls.urls')),
    re_path(r'^(?P<version>(v1|v2))/view/', include('views.urls')),
    re_path(r'^(?P<version>(v1))/chat/', include('chat.urls')),

    re_path(r'^(?P<version>(v1))/publicity_status/all/$', GetPublicityStatusView.as_view(),
            name='list_publicity_status'),

    re_path(r'^(?P<version>(v1))/sidebar/$',
            SideBarApiView.as_view(), name="sidebar_view"),

    re_path(r'^(?P<version>(v1))/feed/$',
            FeedContentApiView.as_view(), name='feed_content'),

    re_path(r'^(?P<version>(v1))/comment/reply/$',
            ReplyCommentApiView.as_view(), name='reply_comment'),
    re_path(r'^(?P<version>(v1))/comment/reply/all/(?P<pk>\d+)/$', BrowseCommentReplyApiView.as_view(),
            name='browse_comment_replies'),
    re_path(r'^(?P<version>(v1))/comment/like/(?P<pk>\d+)/$',
            LikeCommentApiView.as_view(), name='like_comment'),
    re_path(r'^(?P<version>(v1))/comment/unlike/(?P<pk>\d+)/$',
            UnlikeCommentApiView.as_view(), name='unlike_comment'),
    re_path(r'^(?P<version>(v1))/comment/remove/(?P<pk>\d+)/$',
            RemoveCommentApiView.as_view(), name='remove_comment'),
    re_path(r'^(?P<version>(v1))/comment/detail/(?P<pk>\d+)/$',
            CommentDetailApiView.as_view(), name='comment_detail'),

    re_path(r'^(?P<version>(v1))/search/$',
            SearchResultsApiView.as_view(), name='search_results'),
    re_path(r'^(?P<version>(v1))/search/count/$',
            SearchResultsCountApiView.as_view(), name='search_results_count'),
    re_path(r'^(?P<version>(v1))/telegram/opt-in/$',
            TelegramOptInApiView.as_view(), name='telegram_opt_in'),
]
