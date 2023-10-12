from django.urls import re_path

from .views import (BlockUserApiView, BlockedUsersListApiView, GetUsernamesApiView,
                    FollowUserApiView, ReportAccountApiView, UserProfileApiView, GetSubscriptionInfo,
                    EditProfileApiView, LoggedInProfileView,
                    AnonymousProfileView, FollowUserView,
                    GetUsernamesAjaxView, UsersListApiView, RemoveProfileImagesApiView,
                    UserDetailApiView, RecommendedAccountsApiView,
                    GetProfileItemsCountApiView, RefillWalletApiView, ProfilePhotoUploadApiView,
                RegisterWithPhoneApiView,)

app_name = 'users'

urlpatterns = [
    re_path(r'^user/(?P<username>.+)/$', AnonymousProfileView.as_view(),
            name='anonymous_profile'),
    re_path(r'^profile/$', LoggedInProfileView.as_view(),
            name='logged_in_profile'),
    re_path(r'^follow/$', FollowUserView.as_view(), name='legacy_follow_user'),
    re_path(r'get_usernames_legacy/$', GetUsernamesAjaxView.as_view(),
            name='get_usernames_ajax'),

    re_path(r'^get_usernames/$',
            GetUsernamesApiView.as_view(), name='get_usernames'),
    re_path(r'^(?P<pk>\d+)/$',
            UserDetailApiView.as_view(), name='user_detail'),

    re_path(r'^follow/(?P<pk>\d+)/$',
            FollowUserApiView.as_view(), name='follow_user'),

    re_path(r'^block/(?P<pk>\d+)/$',
            BlockUserApiView.as_view(), name='block_user'),
    re_path(r'^block/all/$', BlockedUsersListApiView.as_view(),
            name='blocked_users_list'),

    re_path(r'^profile/(?P<pk>\d+)/$',
            UserProfileApiView.as_view(), name='profile_user'),
    re_path(r'^profile/count/(?P<pk>\d+)/$',
            GetProfileItemsCountApiView.as_view(), name='profile_items_count'),
    re_path(r'^profile/photo/remove/$',
            RemoveProfileImagesApiView.as_view(), name='remove_profile_images'),

    re_path(r'^edit/$', EditProfileApiView.as_view(), name='edit_user'),
    re_path(r'all/$', UsersListApiView.as_view(), name='users_list'),
    re_path(r'^recommended/$', RecommendedAccountsApiView.as_view(),
            name='recommended_accounts'),
    re_path(r'^wallet/refill/$', RefillWalletApiView.as_view(),
            name='refill_wallet'),
    re_path(r'^subscriptions/$', GetSubscriptionInfo.as_view(),
            name='subscription_accounts'),

    re_path(r'^profile/upload/$', ProfilePhotoUploadApiView.as_view(),
            name='upload_profile_photo'),

    re_path(r'^report/(?P<pk>\d+)/$', ReportAccountApiView.as_view(),
            name='report_account'),
    re_path(r'^register-with-phone/$', RegisterWithPhoneApiView.as_view(), 
            name='register_with_phone'),
]
