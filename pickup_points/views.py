from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.cargo_scoping import filter_queryset_by_cargo

from .models import PickupPoint
from .serializers import PickupPointSerializer


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
