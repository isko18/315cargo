from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.permissions import IsOwnerOrStaff

from .models import DeviceToken, Notification
from .serializers import (
    DeviceTokenSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
)
from .services import get_or_create_preference


class NotificationViewSet(ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    queryset = Notification.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        queryset = Notification.objects.select_related("user")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    @action(detail=True, methods=("post",), url_path="read")
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=("is_read",))
        return Response(
            NotificationSerializer(notification, context={"request": request}).data
        )

    @action(detail=False, methods=("post",), url_path="read-all")
    def read_all(self, request):
        updated = (
            Notification.objects.filter(user=request.user, is_read=False)
            .update(is_read=True)
        )
        return Response({"updated": updated})

    @action(detail=False, methods=("get",), url_path="unread-count")
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"count": count})


class DeviceTokenViewSet(ModelViewSet):
    serializer_class = DeviceTokenSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    http_method_names = ("post", "get", "patch", "delete", "head", "options")
    queryset = DeviceToken.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DeviceToken.objects.none()
        queryset = DeviceToken.objects.select_related("user")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class NotificationPreferenceAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = NotificationPreferenceSerializer

    @extend_schema(tags=["profile"], responses={200: NotificationPreferenceSerializer})
    def get(self, request):
        preference = get_or_create_preference(request.user)
        return Response(NotificationPreferenceSerializer(preference).data)

    @extend_schema(tags=["profile"], request=NotificationPreferenceSerializer, responses={200: NotificationPreferenceSerializer})
    def patch(self, request):
        preference = get_or_create_preference(request.user)
        serializer = NotificationPreferenceSerializer(
            preference, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
