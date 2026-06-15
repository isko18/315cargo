from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.cargo_scoping import filter_queryset_by_cargo
from common.permissions import IsCargoManager

from .models import PickupPoint
from .serializers import ManagedPickupPointSerializer, PickupPointSerializer


class PickupPointViewSet(ReadOnlyModelViewSet):
    serializer_class = PickupPointSerializer
    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = PickupPoint.objects.filter(is_active=True).select_related("cargo")
        cargo_id = self.request.query_params.get("cargo")
        if cargo_id:
            return queryset.filter(cargo_id=cargo_id)
        if self.request.user.is_authenticated:
            return filter_queryset_by_cargo(queryset, self.request.user)
        return queryset.none()


class ManagedPickupPointViewSet(ModelViewSet):
    """Панель владельца карго: CRUD своих ПВЗ."""

    serializer_class = ManagedPickupPointSerializer
    permission_classes = (IsAuthenticated, IsCargoManager)
    queryset = PickupPoint.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PickupPoint.objects.none()
        queryset = PickupPoint.objects.select_related("cargo")
        return filter_queryset_by_cargo(queryset, self.request.user)

    def perform_create(self, serializer):
        cargo = self.request.user.cargo
        if cargo is None:
            raise ValidationError(
                "Создание ПВЗ доступно только владельцу карго-центра"
            )
        serializer.save(cargo=cargo)
