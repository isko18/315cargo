from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from integrations.marketplaces import PINDUODUO, TAOBAO
from integrations.serializers import (
    MarketplaceAccountSerializer,
    MarketplaceConnectSerializer,
    MarketplaceIngestSerializer,
    MarketplaceWebhookSerializer,
)
from integrations.services import MarketplaceSyncService


class MarketplaceIntegrationViewSet(GenericViewSet):
    """Общий набор ручек интеграции. Маркетплейс задаётся в наследнике.

    URL остаются раздельными (``/api/integrations/pinduoduo/`` и
    ``/api/integrations/taobao/``): приложение работает с ними как с разными
    подключениями, а контракт у них одинаковый.
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = MarketplaceAccountSerializer
    marketplace = PINDUODUO

    def get_service(self, user=None):
        return MarketplaceSyncService(user or self.request.user, marketplace=self.marketplace)

    @extend_schema(request=MarketplaceConnectSerializer, responses={200: MarketplaceAccountSerializer})
    @action(detail=False, methods=("post",), url_path="connect")
    def connect(self, request):
        serializer = MarketplaceConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = self.get_service().connect(
            serializer.validated_data.get("session_data"), request=request
        )
        return Response(MarketplaceAccountSerializer(account).data)

    @action(detail=False, methods=("post",), url_path="disconnect")
    def disconnect(self, request):
        account = self.get_service().disconnect(request=request)
        return Response(MarketplaceAccountSerializer(account).data)

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
        return Response(MarketplaceAccountSerializer(account).data)

    @extend_schema(request=MarketplaceIngestSerializer, responses={200: dict})
    @action(detail=False, methods=("post",), url_path="ingest")
    def ingest(self, request):
        """Клиентское приложение шлёт сюда заказы, перехваченные из WebView."""
        serializer = MarketplaceIngestSerializer(data=request.data)
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
        """Приложение сообщает, что WebView запросил повторный вход."""
        reason = (request.data or {}).get("reason") or ""
        account = self.get_service().mark_session_expired(
            reason=str(reason), request=request
        )
        return Response(MarketplaceAccountSerializer(account).data)

    @extend_schema(request=MarketplaceWebhookSerializer, responses={200: dict})
    @action(
        detail=False,
        methods=("post",),
        url_path="webhook",
        permission_classes=(IsAdminUser,),
    )
    def webhook(self, request):
        serializer = MarketplaceWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        # client_code уникален только внутри карго — ограничиваем поиск карго
        # запрашивающего админа, иначе вебхук занесёт заказы клиенту чужого
        # карго. Супер-владелец (без карго) ищет глобально, но однозначно.
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


class PinduoduoIntegrationViewSet(MarketplaceIntegrationViewSet):
    marketplace = PINDUODUO


class TaobaoIntegrationViewSet(MarketplaceIntegrationViewSet):
    marketplace = TAOBAO
