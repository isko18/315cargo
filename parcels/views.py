from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.cargo_scoping import filter_owned_queryset
from common.permissions import IsOwnerOrStaff

from .filters import ParcelFilter
from .models import Parcel
from .serializers import ParcelSerializer, ParcelStatusHistorySerializer


class ParcelViewSet(ReadOnlyModelViewSet):
    serializer_class = ParcelSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    filterset_class = ParcelFilter
    queryset = Parcel.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Parcel.objects.none()
        queryset = Parcel.objects.select_related("user", "order")
        return filter_owned_queryset(queryset, self.request.user)

    @action(detail=True, methods=("get",), url_path="history")
    def history(self, request, pk=None):
        parcel = self.get_object()
        serializer = ParcelStatusHistorySerializer(parcel.history.select_related("changed_by"), many=True)
        return Response(serializer.data)
