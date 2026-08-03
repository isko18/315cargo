from rest_framework import serializers

from pickup_points.models import PickupPoint

from .models import CargoCompany


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
            "description",
            "logo",
            "phone",
            "address",
            "price_per_kg_usd",
            "pickup_points",
        )

    def get_pickup_points(self, obj):
        points = obj.pickup_points.filter(is_active=True)
        return PickupPointBriefSerializer(points, many=True).data


class MyCargoSerializer(serializers.ModelSerializer):
    """Профиль карго для редактирования владельцем (slug/is_active read-only)."""

    price_per_kg_usd = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0
    )

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "logo",
            "phone",
            "address",
            "price_per_kg_usd",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "is_active", "created_at", "updated_at")


class CargoOverviewItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
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

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "phone",
            "address",
            "price_per_kg_usd",
            "is_active",
            "created_at",
            "updated_at",
        )
        # slug задаётся при создании и не меняется (публичный идентификатор).
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class AdminCreateCargoSerializer(serializers.Serializer):
    """Создание карго + его первого администратора одной операцией."""

    # Карго
    title = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=50)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    price_per_kg_usd = serializers.DecimalField(
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

    def validate_owner_phone(self, value):
        from users.services import validate_phone

        return validate_phone(value)

    def create(self, validated_data):
        from django.contrib.auth import get_user_model
        from django.db import transaction

        User = get_user_model()
        with transaction.atomic():
            cargo = CargoCompany.objects.create(
                title=validated_data["title"],
                slug=validated_data["slug"],
                phone=validated_data.get("phone", ""),
                address=validated_data.get("address", ""),
                price_per_kg_usd=validated_data.get("price_per_kg_usd", 0),
            )
            owner = User(
                phone=validated_data["owner_phone"],
                cargo=cargo,
                full_name=validated_data["owner_name"],
                is_cargo_admin=True,
            )
            owner.set_password(validated_data["owner_password"])
            owner.save()
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
