import re

from rest_framework import serializers

from pickup_points.models import PickupPoint

from .models import DEFAULT_CLIENT_CODE_PREFIX, CargoCompany

CARGO_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
# Префикс кода клиента: латиница/кириллица и цифры, 1–6 символов («X», «КК», «KG1»).
CLIENT_CODE_PREFIX_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]{1,6}$")


def normalize_client_code_prefix(value, instance=None):
    """Префикс клиентского кода: формат + уникальность на карго.

    Уникальность обязательна: по клиентскому коду коробку опознают на складе
    в Китае, где лежат посылки всех карго сразу.
    """
    prefix = (value or "").strip()
    if not prefix:
        raise serializers.ValidationError("Префикс не может быть пустым")
    if not CLIENT_CODE_PREFIX_RE.match(prefix):
        raise serializers.ValidationError(
            "Префикс: 1–6 символов, только буквы и цифры, без пробелов"
        )
    qs = CargoCompany.objects.filter(client_code_prefix__iexact=prefix)
    if instance is not None and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError("Этот префикс уже занят другим карго")
    return prefix


def free_client_code_prefix(base=DEFAULT_CLIENT_CODE_PREFIX):
    """Свободный префикс по умолчанию: «C», «C2», «C3»… — префикс уникален."""
    taken = {
        p.casefold()
        for p in CargoCompany.objects.values_list("client_code_prefix", flat=True)
    }
    if base.casefold() not in taken:
        return base
    n = 2
    while f"{base}{n}".casefold() in taken:
        n += 1
    return f"{base}{n}"


def normalize_cargo_code(value, instance=None):
    """Код карго: пусто → None, проверка формата и уникальности без учёта регистра."""
    code = (value or "").strip()
    if not code:
        return None
    if not CARGO_CODE_RE.match(code):
        raise serializers.ValidationError(
            "Код карго: 2–32 символа, только латиница, цифры, «-» и «_»"
        )
    qs = CargoCompany.objects.filter(code__iexact=code)
    if instance is not None and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        raise serializers.ValidationError("Такой код карго уже используется")
    return code


class PickupPointBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPoint
        fields = ("id", "title", "address", "phone", "work_schedule")


class CargoCompanySerializer(serializers.ModelSerializer):
    pickup_points = serializers.SerializerMethodField()

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "code",
            "description",
            "logo",
            "phone",
            "address",
            "price_per_kg_kgs",
            "pickup_points",
        )

    def get_pickup_points(self, obj):
        points = obj.pickup_points.filter(is_active=True)
        return PickupPointBriefSerializer(points, many=True).data


class MyCargoSerializer(serializers.ModelSerializer):
    """Профиль карго для редактирования владельцем (slug/code/is_active read-only)."""

    price_per_kg_kgs = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0
    )
    client_code_next = serializers.CharField(source="next_client_code", read_only=True)

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "code",
            "description",
            "logo",
            "phone",
            "address",
            "price_per_kg_kgs",
            "client_code_prefix",
            "client_code_seq",
            "client_code_next",
            "is_active",
            "created_at",
            "updated_at",
        )
        # Код карго назначает супер-владелец — карго его только видит.
        # Счётчик выданных кодов только на чтение: сдвигать его вручную нельзя.
        read_only_fields = (
            "id",
            "slug",
            "code",
            "client_code_seq",
            "is_active",
            "created_at",
            "updated_at",
        )

    def validate_client_code_prefix(self, value):
        return normalize_client_code_prefix(value, instance=self.instance)


class CargoOverviewItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    code = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    users_count = serializers.IntegerField()
    parcels_count = serializers.IntegerField()
    orders_count = serializers.IntegerField()
    pickup_points_count = serializers.IntegerField()


class AdminOverviewSerializer(serializers.Serializer):
    totals = serializers.DictField()
    per_cargo = CargoOverviewItemSerializer(many=True)


class AdminCargoSerializer(serializers.ModelSerializer):
    """Просмотр/редактирование карго главным владельцем."""

    code = serializers.CharField(
        max_length=32, required=False, allow_blank=True, allow_null=True
    )
    client_code_next = serializers.CharField(source="next_client_code", read_only=True)

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "code",
            "phone",
            "address",
            "price_per_kg_kgs",
            "client_code_prefix",
            "client_code_seq",
            "client_code_next",
            "is_active",
            "created_at",
            "updated_at",
        )
        # slug задаётся при создании и не меняется (публичный идентификатор).
        read_only_fields = ("id", "slug", "client_code_seq", "created_at", "updated_at")

    def validate_code(self, value):
        return normalize_cargo_code(value, instance=self.instance)

    def validate_client_code_prefix(self, value):
        return normalize_client_code_prefix(value, instance=self.instance)


class AdminCreateCargoSerializer(serializers.Serializer):
    """Создание карго + его первого администратора одной операцией."""

    # Карго
    title = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=50)
    code = serializers.CharField(
        max_length=32, required=False, allow_blank=True, allow_null=True, default=""
    )
    client_code_prefix = serializers.CharField(max_length=6, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    price_per_kg_kgs = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, default=0
    )
    # Владелец (администратор карго)
    owner_name = serializers.CharField(max_length=255)
    owner_phone = serializers.CharField(max_length=32)
    owner_password = serializers.CharField(min_length=6, write_only=True)

    def validate_slug(self, value):
        if CargoCompany.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Карго с таким идентификатором уже существует")
        return value

    def validate_code(self, value):
        return normalize_cargo_code(value)

    def validate_client_code_prefix(self, value):
        return normalize_client_code_prefix(value)

    def validate_owner_phone(self, value):
        from users.services import validate_phone

        return validate_phone(value)

    def create(self, validated_data):
        from django.contrib.auth import get_user_model
        from django.db import transaction

        User = get_user_model()
        with transaction.atomic():
            cargo = CargoCompany.objects.create(
                # Префикс уникален: без явного значения берём первый свободный.
                client_code_prefix=(
                    validated_data.get("client_code_prefix") or free_client_code_prefix()
                ),
                title=validated_data["title"],
                slug=validated_data["slug"],
                code=validated_data.get("code") or None,
                phone=validated_data.get("phone", ""),
                address=validated_data.get("address", ""),
                price_per_kg_kgs=validated_data.get("price_per_kg_kgs", 0),
            )
            owner = User(
                phone=validated_data["owner_phone"],
                cargo=cargo,
                full_name=validated_data["owner_name"],
                is_cargo_admin=True,
            )
            owner.set_password(validated_data["owner_password"])
            owner.save()
        # Владелец тоже получил клиентский код — перечитываем счётчик, чтобы
        # предпросмотр «следующего кода» в ответе был актуальным.
        cargo.refresh_from_db()
        self._cargo = cargo
        self._owner = owner
        return cargo

    def to_representation(self, instance):
        owner = getattr(self, "_owner", None)
        return {
            "cargo": AdminCargoSerializer(instance).data,
            "owner": {
                "id": owner.id if owner else None,
                "full_name": owner.full_name if owner else None,
                "phone": owner.phone if owner else None,
                "login_key": owner.login_key if owner else None,
            },
        }
