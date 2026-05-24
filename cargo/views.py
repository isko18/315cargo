from django.db.models import Prefetch
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ReadOnlyModelViewSet

from pickup_points.models import PickupPoint

from .models import CargoCompany
from .serializers import CargoCompanySerializer


class CargoCompanyViewSet(ReadOnlyModelViewSet):
    """Список карго-центров для выбора при регистрации."""

    serializer_class = CargoCompanySerializer
    permission_classes = (AllowAny,)
    lookup_field = "slug"

    def get_queryset(self):
        active_points = PickupPoint.objects.filter(is_active=True).order_by("title")
        return CargoCompany.objects.filter(is_active=True).prefetch_related(
            Prefetch("pickup_points", queryset=active_points)
        )
