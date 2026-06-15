from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.cargo_scoping import filter_owned_queryset, get_request_cargo_id
from common.permissions import IsCargoManager, IsOwnerOrStaff

from .filters import ParcelFilter
from .models import Parcel
from .serializers import (
    ParcelAssignSerializer,
    ParcelScanSerializer,
    ParcelSerializer,
    ParcelStatusHistorySerializer,
)
from .services import ScanError, scan_parcel

User = get_user_model()

MANAGER_ACTIONS = ("scan", "assign")


class ParcelViewSet(ReadOnlyModelViewSet):
    serializer_class = ParcelSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    filterset_class = ParcelFilter
    queryset = Parcel.objects.none()

    def get_permissions(self):
        if self.action in MANAGER_ACTIONS:
            return [IsAuthenticated(), IsCargoManager()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Parcel.objects.none()
        queryset = Parcel.objects.select_related("user", "order", "cargo")
        return filter_owned_queryset(queryset, self.request.user, cargo_lookup="cargo")

    @action(detail=True, methods=("get",), url_path="history")
    def history(self, request, pk=None):
        parcel = self.get_object()
        serializer = ParcelStatusHistorySerializer(parcel.history.select_related("changed_by"), many=True)
        return Response(serializer.data)

    def _request_cargo(self, request):
        """Карго оператора. Супер обязан указать ?cargo= / cargo в теле."""
        cargo_id = get_request_cargo_id(request.user)
        if cargo_id:
            return request.user.cargo
        if request.user.is_superuser:
            override = request.data.get("cargo") or request.query_params.get("cargo")
            if override:
                from cargo.models import CargoCompany

                return CargoCompany.objects.filter(pk=override).first()
        return None

    @extend_schema(request=ParcelScanSerializer, responses={200: ParcelSerializer})
    @action(detail=False, methods=("post",), url_path="scan")
    def scan(self, request):
        serializer = ParcelScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cargo = self._request_cargo(request)
        try:
            result, parcel = scan_parcel(
                serializer.validated_data["track_number"],
                cargo=cargo,
                actor=request.user,
                status=serializer.validated_data.get("status") or None,
                request=request,
            )
        except ScanError as exc:
            status_code = 409 if exc.code == "conflict" else 400
            return Response({"detail": exc.message, "code": exc.code}, status=status_code)
        return Response(
            {"result": result, "parcel": ParcelSerializer(parcel).data},
            status=200 if result == "updated" else 201,
        )

    @extend_schema(request=ParcelAssignSerializer, responses={200: ParcelSerializer})
    @action(detail=True, methods=("post",), url_path="assign")
    def assign(self, request, pk=None):
        parcel = self.get_object()
        if parcel.user_id is not None:
            return Response(
                {"detail": "Посылка уже привязана к клиенту"}, status=400
            )
        serializer = ParcelAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client_code = serializer.validated_data["client_code"].strip()
        client = User.objects.filter(
            cargo_id=parcel.cargo_id, client_code=client_code
        ).first()
        if client is None:
            return Response(
                {"detail": f"Клиент с кодом {client_code} не найден в карго"},
                status=404,
            )
        parcel.user = client
        parcel.client_code = client_code
        parcel._status_changed_by = request.user
        parcel.save(update_fields=["user", "client_code", "updated_at"])
        return Response(ParcelSerializer(parcel).data)
