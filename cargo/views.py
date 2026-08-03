from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.cargo_scoping import bound_pickup_id
from common.permissions import HasTabAccess, IsCargoManager, IsSuperOwner
from orders.models import Order
from parcels.models import Parcel
from pickup_points.models import PickupPoint

from .models import CargoCompany
from .serializers import (
    AdminCargoSerializer,
    AdminCreateCargoSerializer,
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

    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "tariff"

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


PERIOD_DAYS = {"today": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}


def _num(v):
    return float(v) if v is not None else 0.0


class CargoDashboardAPIView(APIView):
    """Дашборд владельца: детальная статистика своего карго-центра.

    Параметры фильтра (query):
      - ``period``: today | 7d | 30d | 90d | 365d | all (по умолчанию 30d)
      - ``from`` / ``to``: явный диапазон дат YYYY-MM-DD (перекрывает period)
    """

    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "analytics"

    def _resolve_range(self, request):
        """Вернуть (from_date, to_date, key) — границы включительно (date)."""
        today = timezone.localdate()
        raw_from = request.query_params.get("from")
        raw_to = request.query_params.get("to")

        def _parse(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                return None

        d_from, d_to = _parse(raw_from), _parse(raw_to)
        if d_from or d_to:
            d_to = d_to or today
            d_from = d_from or (d_to - timedelta(days=30))
            if d_from > d_to:
                d_from, d_to = d_to, d_from
            return d_from, d_to, "custom"

        key = request.query_params.get("period", "30d")
        if key == "all":
            return None, today, "all"
        days = PERIOD_DAYS.get(key, 30)
        key = key if key in PERIOD_DAYS else "30d"
        return today - timedelta(days=days - 1), today, key

    def get(self, request):
        cargo = getattr(request.user, "cargo", None)
        if cargo is None:
            raise NotFound("У пользователя не задан карго-центр")

        d_from, d_to, period_key = self._resolve_range(request)

        parcels = Parcel.objects.filter(cargo_id=cargo.id)

        # Скоуп по ПВЗ (переключатель владельца): все метрики считаются по
        # посылкам клиентов выбранного пункта выдачи.
        # Оператор, привязанный к ПВЗ, видит аналитику только своего пункта —
        # его выбор принудительный, override из query игнорируется.
        forced_pickup = bound_pickup_id(request.user)
        if forced_pickup:
            pickup_id = str(forced_pickup)
        else:
            pickup_id = request.query_params.get("pickup_point")
        pickup_title = None
        if pickup_id:
            pp = PickupPoint.objects.filter(pk=pickup_id, cargo_id=cargo.id).first()
            if pp is not None:
                parcels = parcels.filter(user__pickup_point_id=pp.id)
                pickup_title = pp.title
            else:
                pickup_id = None

        issued = parcels.filter(status=Parcel.Status.ISSUED)

        # --- Срез по периоду (выдачи по issued_at, приёмка по created_at) ---
        issued_period = issued.filter(issued_at__date__lte=d_to)
        received_period = parcels.filter(created_at__date__lte=d_to)
        if d_from is not None:
            issued_period = issued_period.filter(issued_at__date__gte=d_from)
            received_period = received_period.filter(created_at__date__gte=d_from)

        p_agg = issued_period.aggregate(
            revenue=Sum("delivery_price"), weight=Sum("weight"), count=Count("id")
        )
        p_count = p_agg["count"] or 0
        p_revenue = _num(p_agg["revenue"])
        p_weight = _num(p_agg["weight"])

        # --- Дневной ряд: выдачи и выручка по дням ---
        series_qs = (
            issued_period.annotate(day=TruncDate("issued_at"))
            .values("day")
            .annotate(count=Count("id"), revenue=Sum("delivery_price"))
        )
        by_day = {
            row["day"]: (row["count"], _num(row["revenue"]))
            for row in series_qs
            if row["day"] is not None
        }
        # Непрерывный ряд с нулями (ограничим до ~180 точек для «all»).
        series_start = d_from or (min(by_day) if by_day else d_to)
        span = (d_to - series_start).days
        if span > 180:
            series_start = d_to - timedelta(days=180)
            span = 180
        timeseries = []
        for i in range(span + 1):
            day = series_start + timedelta(days=i)
            c, rev = by_day.get(day, (0, 0.0))
            timeseries.append({"date": day.isoformat(), "count": c, "revenue": round(rev, 2)})

        # --- Топ клиентов по выручке за период ---
        top_clients = [
            {
                "client_code": row["client_code"] or "—",
                "full_name": row["user__full_name"] or "",
                "count": row["count"],
                "revenue": round(_num(row["revenue"]), 2),
            }
            for row in (
                issued_period.filter(user__isnull=False)
                .values("client_code", "user__full_name")
                .annotate(count=Count("id"), revenue=Sum("delivery_price"))
                .order_by("-revenue", "-count")[:5]
            )
        ]

        # --- Разбивка по ПВЗ (текущий снимок, выданные за период) ---
        by_pickup = [
            {
                "title": row["user__pickup_point__title"] or "Без ПВЗ",
                "count": row["count"],
                "revenue": round(_num(row["revenue"]), 2),
            }
            for row in (
                issued_period.values("user__pickup_point__title")
                .annotate(count=Count("id"), revenue=Sum("delivery_price"))
                .order_by("-count")
            )
        ]

        # --- Текущий снимок (не зависит от периода) ---
        parcels_by_status = {
            row["status"]: row["count"]
            for row in parcels.values("status").annotate(count=Count("id"))
        }
        issued_all = issued.aggregate(revenue=Sum("delivery_price"), weight=Sum("weight"))
        totals_all = parcels.aggregate(revenue=Sum("delivery_price"), weight=Sum("weight"))

        # «Клиентов» — только клиенты, без сотрудников/админов.
        users_qs = User.objects.filter(cargo_id=cargo.id, is_staff=False)
        if pickup_id:
            users_qs = users_qs.filter(pickup_point_id=pickup_id)

        data = {
            "cargo": {"id": cargo.id, "title": cargo.title, "slug": cargo.slug},
            "price_per_kg_usd": float(cargo.price_per_kg_usd),
            "pickup": {
                "id": int(pickup_id) if pickup_id else None,
                "title": pickup_title,
            },
            "period": {
                "key": period_key,
                "from": d_from.isoformat() if d_from else None,
                "to": d_to.isoformat(),
            },
            # KPI за выбранный период
            "period_issued_count": p_count,
            "period_revenue_usd": round(p_revenue, 2),
            "period_weight_kg": round(p_weight, 2),
            "period_avg_check_usd": round(p_revenue / p_count, 2) if p_count else 0.0,
            "period_avg_weight_kg": round(p_weight / p_count, 3) if p_count else 0.0,
            "period_received_count": received_period.count(),
            "timeseries": timeseries,
            "top_clients": top_clients,
            "by_pickup": by_pickup,
            # Снимок «всё время»
            "parcels_by_status": parcels_by_status,
            "users_count": users_qs.count(),
            "pickup_points_count": PickupPoint.objects.filter(cargo_id=cargo.id).count(),
            "orders_count": Order.objects.filter(user__in=users_qs).count()
            if pickup_id
            else Order.objects.filter(user__cargo_id=cargo.id).count(),
            "parcels_count": parcels.count(),
            "parcels_pending_count": parcels.filter(user__isnull=True).count(),
            "issued_count": issued.count(),
            "issued_revenue_usd": _num(issued_all["revenue"]),
            "issued_weight_kg": _num(issued_all["weight"]),
            "total_weight_kg": _num(totals_all["weight"]),
            "potential_revenue_usd": _num(totals_all["revenue"]),
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


@extend_schema_view(
    list=extend_schema(tags=["admin"]),
    create=extend_schema(tags=["admin"]),
)
class AdminCargoViewSet(ModelViewSet):
    """Управление карго-центрами главным владельцем.

    ``create`` заводит карго вместе с его первым администратором (владельцем)
    одной операцией — тот сразу может войти в своё карго.
    """

    permission_classes = (IsAuthenticated, IsSuperOwner)
    http_method_names = ("get", "post", "patch", "head", "options")
    queryset = CargoCompany.objects.all().order_by("title")

    def get_serializer_class(self):
        if self.action == "create":
            return AdminCreateCargoSerializer
        return AdminCargoSerializer

    @action(detail=True, methods=("get",), url_path="detail")
    def detail_stats(self, request, pk=None):
        """Детализация карго для супер-владельца: склады (ПВЗ), сотрудники,
        посылки по статусам, тариф и выручка. Один карго целиком."""
        cargo = self.get_object()
        AT = Parcel.Status.AT_PICKUP_POINT
        ISSUED = Parcel.Status.ISSUED

        parcels = Parcel.objects.filter(cargo=cargo)

        # Агрегаты по физическому ПВЗ приёмки.
        p_by_pickup = {
            row["pickup_point_id"]: row
            for row in parcels.values("pickup_point_id").annotate(
                total=Count("id"),
                at_warehouse=Count("id", filter=Q(status=AT, is_archived=False)),
                issued=Count("id", filter=Q(status=ISSUED)),
            )
        }
        clients_by_pickup = {
            row["pickup_point_id"]: row["c"]
            for row in User.objects.filter(cargo=cargo, is_staff=False)
            .values("pickup_point_id")
            .annotate(c=Count("id"))
        }
        staff_by_pickup = {
            row["pickup_point_id"]: row["c"]
            for row in User.objects.filter(cargo=cargo, is_staff=True)
            .values("pickup_point_id")
            .annotate(c=Count("id"))
        }

        pickups = []
        for pp in PickupPoint.objects.filter(cargo=cargo).order_by("title"):
            row = p_by_pickup.get(pp.id, {})
            pickups.append(
                {
                    "id": pp.id,
                    "title": pp.title,
                    "address": pp.address,
                    "is_active": pp.is_active,
                    "clients": clients_by_pickup.get(pp.id, 0),
                    "staff": staff_by_pickup.get(pp.id, 0),
                    "parcels": row.get("total", 0),
                    "at_warehouse": row.get("at_warehouse", 0),
                    "issued": row.get("issued", 0),
                }
            )

        staff = [
            {
                "id": row["id"],
                "full_name": row["full_name"],
                "phone": row["phone"],
                "is_cargo_admin": row["is_cargo_admin"],
                "is_china_staff": row["is_china_staff"],
                "is_active": row["is_active"],
                "pickup_point_title": row["pickup_point__title"],
            }
            for row in User.objects.filter(cargo=cargo, is_staff=True)
            .order_by("-is_cargo_admin", "full_name")
            .values(
                "id",
                "full_name",
                "phone",
                "is_cargo_admin",
                "is_china_staff",
                "is_active",
                "pickup_point__title",
            )
        ]

        parcels_by_status = {
            row["status"]: row["count"]
            for row in parcels.values("status").annotate(count=Count("id"))
        }
        issued_agg = parcels.filter(status=ISSUED).aggregate(
            revenue=Sum("delivery_price"), weight=Sum("weight")
        )

        return Response(
            {
                "cargo": {
                    "id": cargo.id,
                    "title": cargo.title,
                    "slug": cargo.slug,
                    "phone": cargo.phone,
                    "address": cargo.address,
                    "price_per_kg_usd": float(cargo.price_per_kg_usd),
                    "is_active": cargo.is_active,
                },
                "totals": {
                    "clients": User.objects.filter(cargo=cargo, is_staff=False).count(),
                    "staff": User.objects.filter(cargo=cargo, is_staff=True).count(),
                    "pickups": len(pickups),
                    "parcels": parcels.count(),
                    "at_warehouse": parcels.filter(status=AT, is_archived=False).count(),
                    "issued": parcels.filter(status=ISSUED).count(),
                    "unassigned_pickup": parcels.filter(pickup_point__isnull=True).count(),
                    "revenue_issued": _num(issued_agg["revenue"]),
                    "weight_issued": _num(issued_agg["weight"]),
                },
                "parcels_by_status": parcels_by_status,
                "pickups": pickups,
                "staff": staff,
            }
        )

    @action(detail=True, methods=("get",))
    def admins(self, request, pk=None):
        """Администраторы (владельцы) выбранного карго."""
        cargo = self.get_object()
        rows = (
            User.objects.filter(cargo=cargo, is_cargo_admin=True, is_superuser=False)
            .order_by("-created_at")
            .values("id", "full_name", "phone", "is_active")
        )
        return Response(list(rows))

    @action(detail=True, methods=("post",), url_path="owner-password")
    def owner_password(self, request, pk=None):
        """Сброс пароля администратора карго."""
        cargo = self.get_object()
        owner_id = request.data.get("owner_id")
        password = request.data.get("password") or ""
        if len(password) < 6:
            return Response({"password": "Минимум 6 символов"}, status=400)
        owner = User.objects.filter(
            pk=owner_id, cargo=cargo, is_cargo_admin=True
        ).first()
        if owner is None:
            return Response(
                {"owner_id": "Администратор не найден в этом карго"}, status=404
            )
        owner.set_password(password)
        owner.save(update_fields=["password"])
        return Response({"detail": "Пароль обновлён"})
