from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from common.audit import log_audit
from common.models import AuditLog
from common.permissions import HasTabAccess, IsCargoManager
from common.throttling import AuthRateThrottle, SmsRateThrottle

from .models import User
from .serializers import (
    AuthResponseSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PasswordLoginSerializer,
    RefreshTokenSerializer,
    SendCodeSerializer,
    StaffSerializer,
    UserSerializer,
    VerifyCodeSerializer,
    ProfileQRSerializer,
)
from .services import issue_tokens_for_user, send_sms_code, verify_sms_code


@extend_schema_view(
    send_code=extend_schema(tags=["auth"]),
    verify_code=extend_schema(tags=["auth"]),
    refresh=extend_schema(tags=["auth"]),
    logout=extend_schema(tags=["auth"]),
)
class AuthViewSet(GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = SendCodeSerializer
    queryset = User.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        return User.objects.none()

    @extend_schema(
        request=SendCodeSerializer,
        responses={200: dict},
        examples=[OpenApiExample("Send code", value={"phone": "+996700000000"})],
    )
    @action(
        detail=False,
        methods=("post",),
        url_path="send-code",
        throttle_classes=(SmsRateThrottle,),
    )
    def send_code(self, request):
        serializer = SendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data.copy()
        send_sms_code(**data)
        payload = {"detail": "SMS code sent"}
        if settings.NIKITA_SMS_TEST:
            payload["warning"] = (
                "NIKITA_SMS_TEST=1: SMS не отправляется на телефон, "
                "только имитация API Nikita. Для реальной доставки поставьте NIKITA_SMS_TEST=0."
            )
        elif settings.SMS_BACKEND == "mock" or (
            settings.SMS_BACKEND == "auto"
            and not (settings.NIKITA_SMS_LOGIN and settings.NIKITA_SMS_PASSWORD)
        ):
            payload["warning"] = (
                "SMS_BACKEND=mock: код записан в лог сервера, SMS на телефон не уходит."
            )
        return Response(payload)

    @extend_schema(request=VerifyCodeSerializer, responses={200: AuthResponseSerializer})
    @action(
        detail=False,
        methods=("post",),
        url_path="verify-code",
        throttle_classes=(AuthRateThrottle,),
    )
    def verify_code(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        verify_sms_code(data["phone"], data["code"], cargo=data["cargo"])

        # Один аккаунт-клиент на номер глобально: если клиент с этим номером уже
        # есть (в любом карго) — это вход в него, а не создание дубля.
        user = (
            User.objects.filter(phone=data["phone"], is_staff=False, is_superuser=False)
            .order_by("id")
            .first()
        )
        is_new_user = user is None

        if is_new_user and (not data.get("pickup_point") or not data.get("full_name")):
            raise ValidationError(
                {"detail": "cargo_id, pickup_point_id and full_name are required for registration"}
            )

        if is_new_user:
            user = User(phone=data["phone"], cargo=data["cargo"])
            user.set_unusable_password()
            try:
                user.save()
            except IntegrityError as exc:
                raise ValidationError({"detail": "Этот номер уже используется"}) from exc

        update_fields = []
        if data.get("pickup_point"):
            user.pickup_point = data["pickup_point"]
            update_fields.append("pickup_point")
        if data.get("full_name"):
            user.full_name = data["full_name"]
            update_fields.append("full_name")
        if update_fields:
            user.save(update_fields=update_fields)

        tokens = issue_tokens_for_user(user)
        log_audit(
            AuditLog.Action.USER_REGISTERED if is_new_user else AuditLog.Action.USER_LOGIN,
            actor=user,
            target_user=user,
            description="SMS-авторизация",
            metadata={"phone": user.phone},
            request=request,
        )
        return Response(
            {
                **tokens,
                "user": UserSerializer(user, context={"request": request}).data,
                "is_new_user": is_new_user,
            }
        )

    @extend_schema(request=PasswordLoginSerializer, responses={200: AuthResponseSerializer})
    @action(
        detail=False,
        methods=("post",),
        url_path="token",
        throttle_classes=(AuthRateThrottle,),
    )
    def token(self, request):
        """Вход по логину+паролю (сотрудники/админы) → JWT."""
        serializer = PasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        tokens = issue_tokens_for_user(user)
        log_audit(
            AuditLog.Action.USER_LOGIN,
            actor=user,
            target_user=user,
            description="Вход по паролю",
            metadata={"login": user.login_key},
            request=request,
        )
        return Response(
            {
                **tokens,
                "user": UserSerializer(user, context={"request": request}).data,
                "is_new_user": False,
            }
        )

    @extend_schema(request=RefreshTokenSerializer, responses={200: dict})
    @action(
        detail=False,
        methods=("post",),
        url_path="refresh",
        throttle_classes=(AuthRateThrottle,),
    )
    def refresh(self, request):
        # Use SimpleJWT's serializer so ROTATE_REFRESH_TOKENS /
        # BLACKLIST_AFTER_ROTATION actually take effect: the old refresh token
        # is blacklisted and a new one is issued. The previous implementation
        # returned the same token, so rotation never happened.
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        return Response(serializer.validated_data)

    @extend_schema(request=LogoutSerializer, responses={204: None})
    @action(
        detail=False,
        methods=("post",),
        permission_classes=(IsAuthenticated,),
        url_path="logout",
    )
    def logout(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass
        log_audit(
            AuditLog.Action.USER_LOGOUT,
            actor=request.user,
            target_user=request.user,
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["profile"], responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(tags=["profile"], request=UserSerializer, responses={200: UserSerializer})
    def patch(self, request):
        serializer = UserSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["profile"], responses={204: None})
    def delete(self, request):
        """Удаление аккаунта: обезличивание PII, деактивация, инвалидация токенов."""
        user = request.user
        if user.phone in settings.OTP_TEST_NUMBERS:
            return Response(
                {"detail": "Тестовый аккаунт не может быть удалён"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Инвалидируем все refresh-токены пользователя.
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken,
                OutstandingToken,
            )

            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)
        except Exception:  # noqa: BLE001 — блэклист опционален
            pass

        # Обезличиваем адреса доставки по городу.
        from city_delivery.models import CityDeliveryRequest

        CityDeliveryRequest.objects.filter(user=user).update(
            recipient_name="", recipient_phone="", address="", comment=""
        )

        log_audit(
            getattr(AuditLog.Action, "USER_DELETED", AuditLog.Action.USER_LOGOUT),
            actor=user,
            target_user=user,
            description="Удаление аккаунта",
            metadata={"user_id": user.id},
            request=request,
        )

        # Обезличиваем и деактивируем (SimpleJWT отвергает неактивных → access мёртв).
        user.full_name = ""
        user.phone = f"deleted-{user.id}"
        user.pickup_point = None
        user.is_active = False
        user.set_unusable_password()
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProfilePasswordAPIView(APIView):
    """Смена собственного пароля из профиля."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["profile"], request=PasswordChangeSerializer, responses={200: dict})
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        log_audit(
            AuditLog.Action.USER_LOGIN,
            actor=user,
            target_user=user,
            description="Смена пароля",
            request=request,
        )
        return Response({"detail": "Пароль обновлён"})


class ProfileQRAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["profile"], responses={200: ProfileQRSerializer})
    def get(self, request):
        user = request.user
        qr_url = (
            request.build_absolute_uri(user.qr_code_image.url)
            if user.qr_code_image
            else None
        )
        return Response({"client_code": user.client_code, "qr_code_image": qr_url})


@extend_schema_view(list=extend_schema(tags=["manage"]), create=extend_schema(tags=["manage"]))
class ManagedStaffViewSet(ModelViewSet):
    """Управление сотрудниками карго: владелец/админ создаёт операторов.

    Cargo-админ работает только в своём карго; супер-владелец — по всем
    (карго указывается в теле)."""

    serializer_class = StaffSerializer
    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "staff"
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    queryset = User.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        qs = (
            User.objects.filter(Q(is_staff=True) | Q(is_cargo_admin=True))
            .exclude(is_superuser=True)
            .select_related("cargo", "pickup_point")
            .order_by("-created_at")
        )
        if self.request.user.is_superuser:
            return qs
        # Оператор склада в Китае — глобальная роль супер-владельца; админам
        # карго он не виден и не управляется ими.
        return qs.filter(cargo_id=self.request.user.cargo_id).exclude(is_china_staff=True)

    def _guard_china(self, serializer):
        # Роль оператора склада в Китае может назначать только супер-владелец.
        if serializer.validated_data.get("is_china_staff") and not self.request.user.is_superuser:
            raise ValidationError(
                {"is_china_staff": "Оператора склада в Китае создаёт только супер-владелец"}
            )

    def perform_create(self, serializer):
        actor = self.request.user
        self._guard_china(serializer)
        if actor.is_superuser:
            if not serializer.validated_data.get("cargo"):
                raise ValidationError({"cargo": "Обязателен для супер-владельца"})
            serializer.save()
        else:
            # Cargo-админ создаёт сотрудника только в своём карго.
            serializer.save(cargo=actor.cargo)

    def perform_update(self, serializer):
        self._guard_china(serializer)
        serializer.save()


@extend_schema_view(list=extend_schema(tags=["manage"]))
class ManagedClientViewSet(GenericViewSet):
    """Клиенты карго в панели: список + история покупок (заказы и посылки).

    Cargo-scoped; оператор, привязанный к ПВЗ, видит только клиентов своего
    пункта выдачи."""

    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "clients"
    queryset = User.objects.none()

    def get_queryset(self):
        from django.db.models import Count

        from common.cargo_scoping import bound_pickup_id, get_request_cargo_id

        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        qs = (
            User.objects.filter(is_staff=False, is_superuser=False)
            .select_related("pickup_point")
            .annotate(orders_count=Count("orders", distinct=True), parcels_count=Count("parcels", distinct=True))
            .order_by("-created_at")
        )
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(cargo_id=cargo_id)
        pickup_id = bound_pickup_id(self.request.user)
        if pickup_id:
            qs = qs.filter(pickup_point_id=pickup_id)
        return qs

    def list(self, request):
        from .serializers import ClientListSerializer

        qs = self.filter_queryset(self.get_queryset())
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(client_code__icontains=search)
            )
        page = self.paginate_queryset(qs)
        data = ClientListSerializer(page if page is not None else qs, many=True).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @action(detail=True, methods=("get",))
    def history(self, request, pk=None):
        from orders.models import Order
        from orders.serializers import OrderSerializer
        from parcels.models import Parcel
        from parcels.serializers import ParcelSerializer

        client = self.get_object()
        orders = Order.objects.filter(user=client).order_by("-created_at")
        parcels = Parcel.objects.filter(user=client).select_related("order").order_by("-created_at")
        return Response(
            {
                "client": {
                    "id": client.id,
                    "full_name": client.full_name,
                    "phone": client.phone,
                    "client_code": client.client_code,
                    "pickup_point_title": getattr(client.pickup_point, "title", None),
                },
                "orders": OrderSerializer(orders, many=True, context={"request": request}).data,
                "parcels": ParcelSerializer(parcels, many=True, context={"request": request}).data,
            }
        )
