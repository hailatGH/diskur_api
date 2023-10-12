import json

import rest_framework.exceptions as exceptions
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework_serializer_extensions.views import SerializerExtensionsAPIViewMixin

from api.enums import ViewType, ShareProvider
from api.mixins import ReportMixin, UpdatePublicityMixin, TrendingMixin, ViewArgumentReactionMixin, ShareMixin, ApplaudMixin, \
    BrowseReactionsMixin, HideMixin, CommentMixin, CreateImageMixin
from api.pagination import SmallResultsSetPagination
from api.serializers import CommentSerializer, CreateCommentSerializer
from notifications.models import Notification, NOTIFICATION_TYPES
from notifications.signals import notify
from users.serializers import MoogtMedaUserSerializer
from views.extensions import BasicViewSerializerExtensions, DetailViewSerializerExtensions
from views.models import View
from views.parsers import NestedMultiPartParser
from views.serializers import ViewReportSerializer, ViewSerializer, ViewImageSerializer, ViewNotificationSerializer


class UpdateViewPublicityStatusView(UpdatePublicityMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ViewSerializer

    def post(self, request, *args, **kwargs):
        visibility = request.data.get("visibility")
        view_id = request.data.get("view_id")
        view = get_object_or_404(View, pk=view_id)

        view = self.update_publicity(view, visibility)

        return Response(self.get_serializer(view).data, status.HTTP_200_OK)


class UploadViewImageApiView(generics.CreateAPIView):
    serializer_class = ViewImageSerializer


class CreateViewApiView(SerializerExtensionsAPIViewMixin, DetailViewSerializerExtensions,
                        CreateImageMixin, generics.CreateAPIView):
    serializer_class = ViewSerializer
    extensions_expand = {'tags'}

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            view = serializer.save()

            self.create_image(view)
            view.refresh_from_db()

        self.extensions_expand = {'tags', 'images'}
        serializer = self.get_serializer(view)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_extensions_mixin_context(self):
        context = super(CreateViewApiView, self).get_extensions_mixin_context()
        exclude = []
        if 'tags' not in self.request.data:
            exclude += ['tags']
        context['exclude'] = set(exclude)
        return context


class DeleteViewApiView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ViewSerializer

    def post(self, request, *args, **kwargs):
        view = self.get_object()
        if view.check_is_content_creator(request.user):
            self.destroy(self, request)
        else:
            raise exceptions.PermissionDenied(
                detail="This user is not the owner of this view")

        return Response(True, status.HTTP_200_OK)

    def get_object(self):
        return get_object_or_404(View, pk=self.kwargs.get('pk'))

    def perform_destroy(self, instance: View):
        super().perform_destroy(instance)
        instance.view_reactions.filter(content__isnull=True).delete()


class DeleteAllViewApiView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        qs = View.objects.filter(user=request.user)
        if qs.count() == 0:
            raise exceptions.NotFound(
                detail="Sorry you currently don't have any views to be deleted.")

        qs.delete()
        return Response(True, status.HTTP_200_OK)


class EditViewApiView(SerializerExtensionsAPIViewMixin,
                      generics.GenericAPIView):
    serializer_class = ViewSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [NestedMultiPartParser, JSONParser]
    extensions_expand = ['tags']

    def post(self, request, *args, **kwargs):
        view_id = self.request.data.get("view_id")
        if not view_id:
            raise exceptions.ValidationError("Request needs view id.")
        view = get_object_or_404(View, pk=view_id)

        content = request.data.get("content", "")
        if view.content != content and content != "":
            request.data['is_edited'] = True

        serializer = self.get_serializer(view, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status.HTTP_200_OK)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['is_update'] = True
        return context


class BrowseViewApiView(SerializerExtensionsAPIViewMixin,
                        TrendingMixin,
                        generics.ListAPIView,
                        BasicViewSerializerExtensions):
    serializer_class = ViewSerializer
    pagination_class = SmallResultsSetPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = View.objects

        if self.request.user.is_authenticated:
            queryset = self.get_serializer_class().publicity_filter(
                queryset, self.request.user.id)
            queryset = queryset.filter_views_by_blocked_users(
                self.request.user)

        queryset = self.get_serializer_class().publicity_filter(
            queryset, self.request.user.id)

        # Filter reaction views without statement.
        queryset = queryset.filter(content__isnull=False, is_draft=False)

        # Check if the request has view_only query param. If so get original views only.
        view_only = json.loads(
            self.request.query_params.get('view_only', 'false'))
        if view_only:
            queryset = queryset.filter(type=ViewType.VIEW.name)

        # Check if the request has reaction_view_only query param. If so get reaction views only.
        reaction_view_only = json.loads(
            self.request.query_params.get('reaction_view_only', 'false'))
        if reaction_view_only:
            queryset = queryset.filter(Q(type=ViewType.VIEW_REACTION.name) | Q(
                type=ViewType.ARGUMENT_REACTION.name))

        # Check if the request has trending query param. If so get trending views.
        is_trending = json.loads(
            self.request.query_params.get('trending', 'false'))

        if is_trending:
            return self.get_overall_score_trending_factor_queryset(queryset)

        return queryset.order_by('-created_at')


class ViewReactionApiView(SerializerExtensionsAPIViewMixin,
                          ViewArgumentReactionMixin,
                          generics.GenericAPIView,
                          DetailViewSerializerExtensions):
    serializer_class = ViewSerializer
    extensions_expand = {'parent', 'images'}
    parser_classes = [NestedMultiPartParser, JSONParser]

    def post(self, request, *args, **kwargs):

        if 'type' not in request.data:
            raise exceptions.ValidationError("Request needs type of reaction.")
        if 'view_id' not in request.data:
            raise exceptions.ValidationError("Request needs view id.")

        view = get_object_or_404(View, pk=request.data['view_id'])

        if view.is_hidden:
            raise exceptions.ValidationError(
                "This view is hidden and can not be reacted to.")

        reaction_view = self.react(request, view, ViewType.VIEW_REACTION.name)

        if request.version == 'v1':
            view = View.objects.get(pk=view.id)
            serialized_data = self.get_serializer(view).data
        elif request.version == 'v2':
            if reaction_view:
                reaction_view = View.objects.get(pk=reaction_view.id)
                serialized_data = self.get_serializer(reaction_view).data
            else:
                view = View.objects.get(pk=view.id)
                serialized_data = self.get_serializer(view).data
        else:
            serialized_data = None

        return Response(serialized_data, status.HTTP_200_OK)


class ViewDetailApiView(SerializerExtensionsAPIViewMixin,
                        generics.RetrieveAPIView,
                        DetailViewSerializerExtensions):
    serializer_class = ViewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return View.objects.all()


class ShareView(ShareMixin,
                generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        view_id = kwargs.get('pk')
        view = get_object_or_404(View, pk=view_id)

        share_count = self.share(request)
        view.stats.func_update_share_count(
            ShareProvider.FACEBOOK.name, share_count)

        return Response(share_count, status=status.HTTP_200_OK)


class ApplaudViewApiView(SerializerExtensionsAPIViewMixin,
                         ApplaudMixin,
                         generics.GenericAPIView,
                         BasicViewSerializerExtensions):
    serializer_class = ViewSerializer
    queryset = View.objects.all()

    def post(self, request, *args, **kwargs):
        view = get_object_or_404(View, pk=kwargs.get('pk'))
        has_applauded = self.maybe_applaud(view, self.request.user)
        view = View.objects.get(pk=view.id)

        if has_applauded and self.request.user != view.user:
            notify.send(recipient=view.user,
                        sender=self.request.user,
                        verb="applauded",
                        send_email=False,
                        send_telegram=True,
                        type=NOTIFICATION_TYPES.view_applaud,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=view,
                        data={'view': ViewNotificationSerializer(view).data},
                        push_notification_title=f'{self.request.user} Applauded',
                        push_notification_description=f'{self.request.user} applauded your view, "{view}"'
                        )
        elif not has_applauded and self.request.user != view.user:
            Notification.objects.remove_notification(
                view, self.request.user, NOTIFICATION_TYPES.view_applaud)

        return Response(self.get_serializer(view).data, status=status.HTTP_200_OK)


class BrowseViewReactionsApiView(BrowseReactionsMixin,
                                 SerializerExtensionsAPIViewMixin,
                                 generics.ListAPIView,
                                 DetailViewSerializerExtensions
                                 ):
    serializer_class = ViewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        view_id = self.kwargs.get('pk')
        view = get_object_or_404(View, pk=view_id)

        queryset = view.view_reactions

        queryset = self.get_serializer_class().publicity_filter(
            queryset, self.request.user.id)

        queryset = queryset.filter(
            content__isnull=False).order_by('-created_at')

        return self.get_reactions_queryset(queryset)


class HideViewApiView(SerializerExtensionsAPIViewMixin, HideMixin, generics.GenericAPIView):
    serializer_class = ViewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        view_id = self.kwargs.get('pk')
        view = get_object_or_404(View, pk=view_id)
        if view.check_is_content_creator(request.user):
            self.hide_unhide(view)
        else:
            raise exceptions.PermissionDenied(
                detail="This user is not the owner of this view")
        return Response(self.get_serializer(view).data, status=status.HTTP_200_OK)


class ViewCommentCreateApiView(CommentMixin, generics.GenericAPIView):
    serializer_class = CreateCommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        view_id = request.data['view_id']

        view = get_object_or_404(View, pk=view_id)

        if view.is_comment_disabled:
            raise exceptions.ValidationError("Comment is disabled.")

        comment = self.comment(request, view)
        serializer = CommentSerializer(
            comment, context=self.get_serializer_context())

        if self.request.user != view.user:
            notify.send(recipient=view.user,
                        sender=self.request.user,
                        verb="commented",
                        send_email=False,
                        send_telegram=True,
                        type=NOTIFICATION_TYPES.view_comment,
                        category=Notification.NOTIFICATION_CATEGORY.normal,
                        target=view,
                        data={'view': ViewNotificationSerializer(view).data,
                              'comment': serializer.data},
                        push_notification_title=f'{self.request.user} commented',
                        push_notification_description=f'{self.request.user} commented on your view, "{view}"'

                        )

        return Response(serializer.data, status.HTTP_201_CREATED)


class ListViewCommentsApiView(SerializerExtensionsAPIViewMixin, CommentMixin, generics.ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = SmallResultsSetPagination
    extensions_expand = ['user__profile']

    def get_queryset(self):
        view_id = self.kwargs.get('pk')
        view = get_object_or_404(View, pk=view_id)

        return self.get_comments(self.request, view)


class GetUsersReactingApiView(generics.ListAPIView, ViewArgumentReactionMixin):
    serializer_class = MoogtMedaUserSerializer

    def get(self, request, *args, **kwargs):
        view = get_object_or_404(View, pk=kwargs.get('pk'))

        self.queryset = self.get_reacting_users(request, view)

        return self.list(request, *args, **kwargs)

class ViewReportApiView(ReportMixin, generics.CreateAPIView):
    serializer_class = ViewReportSerializer
    
    def post(self, request, *args, **kwargs):
        view_id = kwargs.get('pk')
        self.view = get_object_or_404(View, pk=view_id)
        
        self.validate(created_by=self.view.user, reported_by=request.user, queryset=self.view.reports.all())
        return super().post(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        report = serializer.save(view=self.view, reported_by=self.request.user)
        self.notify_admins(report)