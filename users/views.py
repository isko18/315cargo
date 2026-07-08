from django.conf import settings
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
from common.permissions import IsCargoManager
from common.throttling import AuthRateThrottle, SmsRateThrottle

from .models import User
from .serializers import (
    AuthResponseSerializer,
    LogoutSerializer,
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

        user = User.objects.filter(phone=data["phone"], cargo=data["cargo"]).first()
        is_new_user = user is None

        if is_new_user and (not data.get("pickup_point") or not data.get("full_name")):
            raise ValidationError(
                {"detail": "cargo_id, pickup_point_id and full_name are required for registration"}
            )

        if is_new_user:
            user = User(phone=data["phone"], cargo=data["cargo"])
            user.set_unusable_password()
            user.save()

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
    permission_classes = (IsAuthenticated, IsCargoManager)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    queryset = User.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        qs = (
            User.objects.filter(Q(is_staff=True) | Q(is_cargo_admin=True))
            .exclude(is_superuser=True)
            .select_related("cargo")
            .order_by("-created_at")
        )
        if self.request.user.is_superuser:
            return qs
        return qs.filter(cargo_id=self.request.user.cargo_id)

    def perform_create(self, serializer):
        actor = self.request.user
        if actor.is_superuser:
            if not serializer.validated_data.get("cargo"):
                raise ValidationError({"cargo": "Обязателен для супер-владельца"})
            serializer.save()
        else:
            # Cargo-админ создаёт сотрудника только в своём карго.
            serializer.save(cargo=actor.cargo)
