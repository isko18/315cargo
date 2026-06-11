from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from integrations.serializers import (
    PinduoduoAccountSerializer,
    PinduoduoConnectSerializer,
    PinduoduoIngestSerializer,
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

    @extend_schema(request=PinduoduoIngestSerializer, responses={200: dict})
    @action(detail=False, methods=("post",), url_path="ingest")
    def ingest(self, request):
        """Клиентское приложение шлёт сюда заказы, перехваченные из WebView."""
        serializer = PinduoduoIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = self.get_service().ingest_orders(
            serializer.validated_data["orders"], request=request
        )
        return Response(
            {
                "synced": result.synced,
                "created": result.created,
                "updated": result.updated,
                "errors": result.errors,
            }
        )

    @action(detail=False, methods=("post",), url_path="session-expired")
    def session_expired(self, request):
        """Приложение сообщает, что WebView запросил повторный вход в PDD."""
        account = self.get_service().mark_session_expired(request=request)
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
        # client_code is unique only per cargo — scope the lookup to the
        # requesting admin's cargo so a webhook cannot ingest orders into a
        # client of another cargo. A superuser (no cargo) resolves globally but
        # must still be unambiguous.
        user_qs = User.objects.filter(
            client_code=serializer.validated_data["client_code"]
        )
        if not request.user.is_superuser and request.user.cargo_id:
            user_qs = user_qs.filter(cargo_id=request.user.cargo_id)
        matches = list(user_qs[:2])
        if len(matches) > 1:
            return Response(
                {"detail": "client_code is ambiguous across cargos"}, status=409
            )
        user = matches[0] if matches else None
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
