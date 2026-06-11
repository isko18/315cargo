from rest_framework import serializers

from .models import DeviceToken, Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    type_display_name = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "body",
            "type",
            "type_display_name",
            "is_read",
            "data",
            "created_at",
        )
        read_only_fields = (
            "id",
            "title",
            "body",
            "type",
            "type_display_name",
            "data",
            "created_at",
        )


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ("id", "token", "platform", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        # `user` is always the authenticated requester (set in perform_create),
        # never taken from the request body — a client cannot register a token
        # on behalf of someone else. Re-registering a token re-binds it to the
        # current user (device handoff) and reactivates it.
        user = validated_data["user"]
        token = validated_data["token"]
        instance, _ = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                "user": user,
                "platform": validated_data["platform"],
                "is_active": validated_data.get("is_active", True),
            },
        )
        return instance


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "push_enabled",
            "parcel_status_enabled",
            "order_status_enabled",
            "city_delivery_enabled",
            "marketing_enabled",
            "updated_at",
        )
        read_only_fields = ("updated_at",)
