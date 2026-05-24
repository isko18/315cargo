from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from common.audit import log_audit
from common.models import AuditLog
from common.throttling import AuthRateThrottle, SmsRateThrottle

from .models import User
from .serializers import (
    AuthResponseSerializer,
    LogoutSerializer,
    RefreshTokenSerializer,
    SendCodeSerializer,
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
        data.pop("cargo", None)
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
        verify_sms_code(data["phone"], data["code"])

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

    @extend_schema(request=RefreshTokenSerializer, responses={200: dict})
    @action(
        detail=False,
        methods=("post",),
        url_path="refresh",
        throttle_classes=(AuthRateThrottle,),
    )
    def refresh(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            access = str(refresh.access_token)
            new_refresh = str(refresh)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        return Response({"access": access, "refresh": new_refresh})

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
