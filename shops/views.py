from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.cargo_scoping import filter_queryset_by_cargo

from .models import Shop
from .serializers import ShopSerializer


class ShopViewSet(ReadOnlyModelViewSet):
    serializer_class = ShopSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = Shop.objects.filter(is_active=True).select_related("cargo")
        return filter_queryset_by_cargo(queryset, self.request.user)
