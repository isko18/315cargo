from rest_framework import serializers

from cargo.models import CargoCompany
from pickup_points.models import PickupPoint

from .constants import OTP_CODE_LENGTH
from .models import SMSCode, User
from .services import validate_phone


class UserSerializer(serializers.ModelSerializer):
    pickup_point_title = serializers.CharField(source="pickup_point.title", read_only=True)
    cargo_title = serializers.CharField(source="cargo.title", read_only=True)
    is_cargo_admin = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "cargo",
            "cargo_title",
            "phone",
            "full_name",
            "pickup_point",
            "pickup_point_title",
            "client_code",
            "qr_code_image",
            "is_cargo_admin",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "cargo",
            "phone",
            "client_code",
            "qr_code_image",
            "is_cargo_admin",
            "created_at",
            "updated_at",
        )

    def validate_pickup_point(self, pickup_point):
        # A client may only select a pickup point within their own cargo.
        if pickup_point is None:
            return pickup_point
        user = self.instance
        if user and user.cargo_id and pickup_point.cargo_id != user.cargo_id:
            raise serializers.ValidationError(
                "ПВЗ не принадлежит вашему карго-центру."
            )
        return pickup_point


class SendCodeSerializer(serializers.Serializer):
    phone = serializers.CharField()
    cargo_id = serializers.PrimaryKeyRelatedField(
        queryset=CargoCompany.objects.filter(is_active=True),
        source="cargo",
    )
    purpose = serializers.ChoiceField(choices=SMSCode.Purpose.choices, default=SMSCode.Purpose.LOGIN)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate(self, attrs):
        cargo = attrs["cargo"]
        phone = attrs["phone"]
        purpose = attrs.get("purpose", SMSCode.Purpose.LOGIN)
        if purpose == SMSCode.Purpose.LOGIN:
            if not User.objects.filter(phone=phone, cargo=cargo).exists():
                raise serializers.ValidationError(
                    {"phone": "Пользователь не найден в этом карго-центре. Зарегистрируйтесь."}
                )
        return attrs


class VerifyCodeSerializer(serializers.Serializer):
    phone = serializers.CharField()
    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)
    cargo_id = serializers.PrimaryKeyRelatedField(
        queryset=CargoCompany.objects.filter(is_active=True),
        source="cargo",
    )
    pickup_point_id = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.filter(is_active=True),
        source="pickup_point",
        required=False,
        allow_null=True,
    )
    full_name = serializers.CharField(required=False, allow_blank=True)

    def validate_phone(self, value):
        return validate_phone(value)

    def validate(self, attrs):
        cargo = attrs["cargo"]
        pickup_point = attrs.get("pickup_point")
        if pickup_point and pickup_point.cargo_id != cargo.id:
            raise serializers.ValidationError(
                {"pickup_point_id": "ПВЗ не принадлежит выбранному карго-центру."}
            )
        return attrs


class AuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
    is_new_user = serializers.BooleanField()


class ProfileQRSerializer(serializers.Serializer):
    client_code = serializers.CharField(allow_null=True)
    qr_code_image = serializers.URLField(allow_null=True)


class RefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
