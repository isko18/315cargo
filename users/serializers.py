from django.db.models import Q
from rest_framework import serializers

from cargo.models import CargoCompany
from common.tabs import sanitize_tabs, user_allowed_tabs
from pickup_points.models import PickupPoint

from .constants import OTP_CODE_LENGTH
from .models import SMSCode, User
from .services import validate_phone


class UserSerializer(serializers.ModelSerializer):
    pickup_point_title = serializers.CharField(source="pickup_point.title", read_only=True)
    cargo_title = serializers.CharField(source="cargo.title", read_only=True)
    is_cargo_admin = serializers.BooleanField(read_only=True)
    is_china_staff = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    allowed_tabs = serializers.SerializerMethodField()

    def get_allowed_tabs(self, obj):
        # Эффективный список вкладок с учётом роли — для фильтрации меню.
        return user_allowed_tabs(obj)

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
            "is_china_staff",
            "is_staff",
            "is_superuser",
            "allowed_tabs",
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
            "is_china_staff",
            "is_staff",
            "is_superuser",
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


class StaffSerializer(serializers.ModelSerializer):
    """Сотрудник/оператор карго: создание и управление владельцем/админом."""

    cargo_title = serializers.CharField(source="cargo.title", read_only=True)
    pickup_point_title = serializers.CharField(
        source="pickup_point.title", read_only=True, default=None
    )
    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}, min_length=6
    )
    allowed_tabs = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Вкладки, доступные оператору (игнорируется для админа/китай-оператора).",
    )

    class Meta:
        model = User
        fields = (
            "id",
            "phone",
            "full_name",
            "cargo",
            "cargo_title",
            "pickup_point",
            "pickup_point_title",
            "is_cargo_admin",
            "is_china_staff",
            "is_staff",
            "is_active",
            "allowed_tabs",
            "password",
            "created_at",
        )
        read_only_fields = ("id", "cargo_title", "pickup_point_title", "is_staff", "created_at")

    def validate_allowed_tabs(self, value):
        return sanitize_tabs(value)

    def validate(self, attrs):
        # ПВЗ должен принадлежать тому же карго, что и сотрудник.
        pickup = attrs.get("pickup_point")
        if pickup is not None:
            request = self.context.get("request")
            actor = getattr(request, "user", None)
            eff_cargo = attrs.get("cargo") or getattr(self.instance, "cargo", None)
            if eff_cargo is None and actor is not None and not actor.is_superuser:
                eff_cargo = actor.cargo
            if eff_cargo is not None and pickup.cargo_id != eff_cargo.id:
                raise serializers.ValidationError(
                    {"pickup_point": "ПВЗ не принадлежит выбранному карго-центру"}
                )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["is_staff"] = True
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class PasswordChangeSerializer(serializers.Serializer):
    """Смена собственного пароля (сотрудники/админы)."""

    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(
        write_only=True, min_length=6, style={"input_type": "password"}
    )

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.has_usable_password() or not user.check_password(value):
            raise serializers.ValidationError("Неверный текущий пароль")
        return value


class ClientListSerializer(serializers.ModelSerializer):
    """Клиент карго в панели: сводка для списка (с историей покупок отдельно)."""

    pickup_point_title = serializers.CharField(
        source="pickup_point.title", read_only=True, default=None
    )
    orders_count = serializers.IntegerField(read_only=True)
    parcels_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "phone",
            "client_code",
            "pickup_point",
            "pickup_point_title",
            "orders_count",
            "parcels_count",
            "created_at",
        )


class PasswordLoginSerializer(serializers.Serializer):
    """Вход по логину+паролю для сотрудников и админов (не для обычных клиентов)."""

    login = serializers.CharField(help_text="Телефон или login_key")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        login = (attrs.get("login") or "").strip()
        password = attrs.get("password") or ""
        candidates = User.objects.filter(
            Q(login_key=login) | Q(phone=login)
        ).filter(Q(is_staff=True) | Q(is_superuser=True))
        for user in candidates:
            if user.is_active and user.check_password(password):
                attrs["user"] = user
                return attrs
        raise serializers.ValidationError(
            {"detail": "Неверный логин или пароль, либо нет прав сотрудника"}
        )


class RefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
