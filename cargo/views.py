from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.permissions import IsCargoManager, IsSuperOwner
from orders.models import Order
from parcels.models import Parcel
from pickup_points.models import PickupPoint

from .models import CargoCompany
from .serializers import (
    AdminOverviewSerializer,
    CargoCompanySerializer,
    MyCargoSerializer,
)

User = get_user_model()


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


class MyCargoAPIView(APIView):
    """Профиль своего карго-центра: просмотр и редактирование владельцем."""

    permission_classes = (IsAuthenticated, IsCargoManager)

    def get_object(self):
        cargo = getattr(self.request.user, "cargo", None)
        if cargo is None:
            raise NotFound("У пользователя не задан карго-центр")
        return cargo

    @extend_schema(responses={200: MyCargoSerializer})
    def get(self, request):
        return Response(MyCargoSerializer(self.get_object()).data)

    @extend_schema(request=MyCargoSerializer, responses={200: MyCargoSerializer})
    def patch(self, request):
        serializer = MyCargoSerializer(
            self.get_object(), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CargoDashboardAPIView(APIView):
    """Дашборд владельца: статистика своего карго-центра."""

    permission_classes = (IsAuthenticated, IsCargoManager)

    def get(self, request):
        cargo = getattr(request.user, "cargo", None)
        if cargo is None:
            raise NotFound("У пользователя не задан карго-центр")

        parcels = Parcel.objects.filter(cargo_id=cargo.id)
        parcels_by_status = {
            row["status"]: row["count"]
            for row in parcels.values("status").annotate(count=Count("id"))
        }
        data = {
            "cargo": {"id": cargo.id, "title": cargo.title, "slug": cargo.slug},
            "users_count": User.objects.filter(cargo_id=cargo.id).count(),
            "pickup_points_count": PickupPoint.objects.filter(cargo_id=cargo.id).count(),
            "orders_count": Order.objects.filter(user__cargo_id=cargo.id).count(),
            "parcels_count": parcels.count(),
            "parcels_pending_count": parcels.filter(user__isnull=True).count(),
            "parcels_by_status": parcels_by_status,
        }
        return Response(data)


class AdminOverviewAPIView(APIView):
    """Дашборд главного владельца: сводная статистика по всем карго."""

    permission_classes = (IsAuthenticated, IsSuperOwner)

    @extend_schema(responses={200: AdminOverviewSerializer})
    def get(self, request):
        per_cargo_qs = CargoCompany.objects.annotate(
            users_count=Count("users", distinct=True),
            parcels_count=Count("parcels", distinct=True),
            pickup_points_count=Count("pickup_points", distinct=True),
            orders_count=Count("users__orders", distinct=True),
        ).order_by("title")
        per_cargo = [
            {
                "id": c.id,
                "title": c.title,
                "slug": c.slug,
                "is_active": c.is_active,
                "users_count": c.users_count,
                "parcels_count": c.parcels_count,
                "orders_count": c.orders_count,
                "pickup_points_count": c.pickup_points_count,
            }
            for c in per_cargo_qs
        ]
        totals = {
            "cargo_count": CargoCompany.objects.count(),
            "active_cargo_count": CargoCompany.objects.filter(is_active=True).count(),
            "user_count": User.objects.count(),
            "parcel_count": Parcel.objects.count(),
            "order_count": Order.objects.count(),
            "pickup_point_count": PickupPoint.objects.count(),
        }
        return Response({"totals": totals, "per_cargo": per_cargo})
