from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from integrations.serializers import (
    PinduoduoAccountSerializer,
    PinduoduoConnectSerializer,
    PinduoduoWebhookSerializer,
)

from .services import PinduoduoSyncService


class PinduoduoIntegrationViewSet(GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = PinduoduoAccountSerializer

    def get_service(self, user=None):
        return PinduoduoSyncService(user or self.request.user)

    @extend_schema(request=PinduoduoConnectSerializer, responses={200: PinduoduoAccountSerializer})
    @action(detail=False, methods=("post",), url_path="connect")
    def connect(self, request):
        serializer = PinduoduoConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = self.get_service().connect(
            serializer.validated_data.get("session_data"), request=request
        )
        return Response(PinduoduoAccountSerializer(account).data)

    @action(detail=False, methods=("post",), url_path="disconnect")
    def disconnect(self, request):
        account = self.get_service().disconnect(request=request)
        return Response(PinduoduoAccountSerializer(account).data)

    @action(detail=False, methods=("post",), url_path="sync")
    def sync(self, request):
        result = self.get_service().sync_orders(request=request)
        return Response(
            {
                "synced": result.synced,
                "created": result.created,
                "updated": result.updated,
                "message": result.message,
                "errors": result.errors,
            }
        )

    @action(detail=False, methods=("get",), url_path="status")
    def status(self, request):
        account = self.get_service().account
        return Response(PinduoduoAccountSerializer(account).data)

    @extend_schema(request=PinduoduoWebhookSerializer, responses={200: dict})
    @action(
        detail=False,
        methods=("post",),
        url_path="webhook",
        permission_classes=(IsAdminUser,),
    )
    def webhook(self, request):
        serializer = PinduoduoWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.filter(
            client_code=serializer.validated_data["client_code"]
        ).first()
        if not user:
            return Response({"detail": "client not found"}, status=404)
        result = self.get_service(user=user).ingest_webhook_payload(
            {"orders": serializer.validated_data["orders"]}, request=request
        )
        return Response(
            {
                "synced": result.synced,
                "created": result.created,
                "updated": result.updated,
                "errors": result.errors,
            }
        )
