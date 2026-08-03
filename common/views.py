from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeliveryAddress
from .permissions import IsSuperOwner
from .serializers import DeliveryAddressSerializer


class DeliveryAddressAPIView(APIView):
    """Глобальный адрес доставки (склад в Китае для PDD).

    GET — любой авторизованный (клиент получает адрес с вшитым своим кодом).
    PUT/PATCH — только супер-владелец: он один заполняет адрес, остальные карго
    используют этот же адрес.
    """

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), IsSuperOwner()]
        return [IsAuthenticated()]

    @extend_schema(tags=["delivery-address"], responses={200: DeliveryAddressSerializer})
    def get(self, request):
        obj = DeliveryAddress.get_solo()
        return Response(DeliveryAddressSerializer(obj, context={"request": request}).data)

    @extend_schema(
        tags=["delivery-address"],
        request=DeliveryAddressSerializer,
        responses={200: DeliveryAddressSerializer},
    )
    def put(self, request):
        return self._save(request, partial=False)

    @extend_schema(
        tags=["delivery-address"],
        request=DeliveryAddressSerializer,
        responses={200: DeliveryAddressSerializer},
    )
    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, partial):
        obj = DeliveryAddress.get_solo()
        serializer = DeliveryAddressSerializer(
            obj, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)
