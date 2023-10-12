from django.urls.conf import re_path

from chat.api.views import (SendRegularMessageApiView, ListConversationApiView, PrioritizeConversationApiView,
                            UnPrioritizeConversationApiView, RecentConversationsApiView, ListMessageApiView,
                            ReadMessageApiView,
                            GetConversationWithSomeone, DeleteMessageApiView, ReplyMessageApiView,
                            ForwardMessageApiView,
                            CountPendingMessagesOfConversationApiView, GetMoogtInvitationMessageApiView,
                            GetInvitationMessageApiView, GetMiniSuggestionMessageApiView)
from chat.api.views import UnreadConversationCountApiView

app_name = 'chat'

urlpatterns = [
    re_path(r'^conversation/all/$',
            ListConversationApiView.as_view(),
            name='conversation_list'),

    re_path(r'^conversation/recent/$',
            RecentConversationsApiView.as_view(),
            name='recent_conversations'),

    re_path(r'^conversation/prioritize/(?P<pk>\d+)/$',
            PrioritizeConversationApiView.as_view(),
            name='prioritize_conversations'),

    re_path(r'^conversation/unprioritize/(?P<pk>\d+)/$',
            UnPrioritizeConversationApiView.as_view(),
            name='unprioritize_conversations'),

    re_path(r'^conversation/with/(?P<pk>\d+)/$',
            GetConversationWithSomeone.as_view(),
            name='get_conversation_with_someone'),

    re_path(r'^message/all/(?P<pk>\d+)/$',
            ListMessageApiView.as_view(),
            name='message_list'),

    re_path(r'^message/send/$',
            SendRegularMessageApiView.as_view(),
            name='send_message'),

    re_path(r'message/forward/(?P<pk>\d+)/$',
            ForwardMessageApiView.as_view(),
            name='forward_message'),

    re_path(r'^message/reply/$',
            ReplyMessageApiView.as_view(),
            name='reply_message'),

    re_path(r'^message/read/$',
            ReadMessageApiView.as_view(),
            name="read_message"),

    re_path(r'^message/delete/(?P<pk>\d+)/$',
            DeleteMessageApiView.as_view(),
            name="delete_message"),

    re_path(r'^message/pending/count/(?P<pk>\d+)/$',
            CountPendingMessagesOfConversationApiView.as_view(),
            name='count_pending_messages'),

    re_path(r'^message/invitation/moogt/(?P<pk>\d+)/$',
            GetMoogtInvitationMessageApiView.as_view(),
            name='get_moogt_invitation_message'),

    re_path(r'^message/invitation/(?P<pk>\d+)/$',
            GetInvitationMessageApiView.as_view(),
            name='get_invitation_message'),

    re_path(r'^message/mini-suggestion/(?P<pk>\d+)/$',
            GetMiniSuggestionMessageApiView.as_view(),
            name='get_mini_suggestion_message'),

    re_path(r'^message/unread-conversation-count/$',
            UnreadConversationCountApiView.as_view(),
            name='unread_conversation_count'),
]
