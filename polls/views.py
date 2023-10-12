import json

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_comments_xtd.api.serializers import WriteCommentSerializer
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin

from api.enums import ShareProvider
from api.mixins import ReportMixin, TrendingMixin, ShareMixin, UpdatePublicityMixin, CommentMixin
from api.pagination import SmallResultsSetPagination
from api.serializers import CommentSerializer
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from .models import Poll, PollOption
from .serializers import PollReportSerializer, PollSerializer, PollNotificationSerializer


# Create your views here.
class CreatePollApiView(SerializerExtensionsAPIViewMixin, generics.CreateAPIView):
    serializer_class = PollSerializer

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class BrowsePollApiView(SerializerExtensionsAPIViewMixin,
                        TrendingMixin,
                        generics.ListAPIView):
    serializer_class = PollSerializer
    pagination_class = SmallResultsSetPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Poll.objects.get_polls_for_user(self.request.user).all()

        if self.request.user.is_authenticated:
            queryset = queryset.filter_poll_by_blocked_user(self.request.user)

        # Check if the request has trending query param. If so get trending views.
        is_trending = json.loads(
            self.request.query_params.get('trending', 'false'))
        if is_trending:
            return self.get_overall_score_trending_factor_queryset(queryset)

        return queryset.order_by('-created_at')


class PollDetailApiView(SerializerExtensionsAPIViewMixin,
                        generics.RetrieveAPIView):
    serializer_class = PollSerializer

    def get_queryset(self):
        return Poll.objects.get_polls_for_user(self.request.user)

    def get_object(self):
        obj: Poll = super().get_object()
        if obj.has_expired() and not obj.get_is_closed():
            obj.set_is_closed(True)
            obj.save()

            # Send poll_closed notification to the
            notify.send(
                recipient=obj.user,
                sender=obj.user,
                verb="closed",
                target=obj,
                send_email=False,
                send_telegram=True,
                type=NOTIFICATION_TYPES.poll_closed,
                data={
                    'poll': PollNotificationSerializer(obj).data
                },
                push_notification_title='Your Poll Closed',
                push_notification_description=f'Your Poll, “{obj}” closed.'

            )

        return obj


class VotePollApiView(generics.GenericAPIView):
    http_method_names = ['post']
    serializer_class = PollSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        option_id = kwargs.get('pk')
        option = get_object_or_404(PollOption, pk=option_id)
        has_voted = self.maybe_vote(request.user, option)

        if has_voted:
            notify.send(
                recipient=option.poll.user,
                sender=self.request.user,
                verb="voted",
                target=option.poll,
                send_email=False,
                send_telegram=True,
                type=NOTIFICATION_TYPES.poll_vote,
                data={
                    'poll': PollNotificationSerializer(option.poll).data
                })

        return Response(self.get_serializer(Poll.objects.get_polls_for_user(request.user).get(id=option.poll.id)).data,
                        status.HTTP_200_OK)

    def maybe_vote(self, user, option: PollOption):
        if option.poll.has_user_voted(user):
            raise ValidationError("This user has already voted on this poll")

        elif option.poll.end_date < timezone.now():
            raise ValidationError("This poll has expired")

        elif option.poll.user == user:
            raise ValidationError("User can't vote on their own poll")
        else:
            option.votes.add(user)
            return True


class PollCommentCreateApiView(CommentMixin, generics.GenericAPIView):
    serializer_class = WriteCommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        poll_id = request.data.get('poll_id')

        poll = get_object_or_404(Poll, pk=poll_id)

        comment = self.comment(request, poll)
        serializer = CommentSerializer(
            comment, context=self.get_serializer_context())

        if self.request.user != poll.user:
            notify.send(recipient=poll.user,
                        sender=self.request.user,
                        verb="commented",
                        send_email=False,
                        send_telegram=True,
                        type=NOTIFICATION_TYPES.poll_comment,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=poll,
                        data={'poll': PollNotificationSerializer(poll).data,
                              'comment': serializer.data},
                        push_notification_title=f'{self.request.user} Commented on your Poll',
                        push_notification_description=f'{self.request.user} commented on your Poll, "{poll}"'

                        )

        return Response(serializer.data, status.HTTP_201_CREATED)


class ListPollCommentsApiView(SerializerExtensionsAPIViewMixin, CommentMixin, generics.ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = SmallResultsSetPagination
    extensions_expand = ['user__profile']

    def get_queryset(self):
        poll_id = self.kwargs.get('pk')
        poll = get_object_or_404(Poll, pk=poll_id)

        return self.get_comments(self.request, poll)


class SharePoll(ShareMixin,
                generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        poll_id = kwargs.get('pk')
        poll = get_object_or_404(Poll, pk=poll_id)

        share_count = self.share(request)
        poll.stats.func_update_share_count(
            ShareProvider.FACEBOOK.name, share_count)

        return Response(share_count, status=status.HTTP_200_OK)


class UpdatePollPublicityStatusView(UpdatePublicityMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PollSerializer

    def post(self, request, *args, **kwargs):
        visibility = request.data.get("visibility")
        poll_id = request.data.get("poll_id")

        poll = get_object_or_404(Poll, pk=poll_id)

        poll = self.update_publicity(poll, visibility)

        return Response(self.get_serializer(poll).data, status.HTTP_200_OK)


class DeletePollApiView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        poll_id = kwargs.get("pk")
        poll = get_object_or_404(Poll, pk=poll_id)

        if poll.user != self.request.user:
            raise ValidationError('You are not the owner of this poll.')

        poll.delete()

        return Response({'success': True})

class ReportPollApiView(ReportMixin, generics.CreateAPIView):
    serializer_class = PollReportSerializer
    
    def post(self, request, *args, **kwargs):
        poll_id = kwargs.get('pk')
        self.poll = get_object_or_404(Poll, pk=poll_id)
        
        self.validate(created_by=self.poll.user, 
                      reported_by=request.user, 
                      queryset=self.poll.reports.all())
        
        return super().post(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        report = serializer.save(poll=self.poll, reported_by=self.request.user)
        self.notify_admins(report)