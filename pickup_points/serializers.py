from rest_framework import serializers

from .models import PickupPoint


class PickupPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPoint
        fields = ("id", "title", "address", "phone", "work_schedule")
