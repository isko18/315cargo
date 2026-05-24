from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.cargo_scoping import filter_owned_queryset
from common.permissions import IsOwnerOrStaff

from .filters import OrderFilter
from .models import Order
from .serializers import ManualOrderSerializer, OrderSerializer


class OrderViewSet(ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    filterset_class = OrderFilter
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        queryset = Order.objects.select_related("user")
        return filter_owned_queryset(queryset, self.request.user)

    def get_serializer_class(self):
        if self.action == "manual":
            return ManualOrderSerializer
        return OrderSerializer

    @extend_schema(request=ManualOrderSerializer, responses={201: OrderSerializer})
    @action(detail=False, methods=("post",), url_path="manual")
    def manual(self, request):
        serializer = ManualOrderSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save(user=request.user, source=Order.Source.MANUAL, status=Order.Status.CREATED)
        return Response(OrderSerializer(order, context={"request": request}).data, status=201)
