from collections.abc import Mapping

from rest_framework import serializers

from . import services
from .models import Allocation, ParkingSpace, Vehicle, normalize_plate


def identifier(**kwargs):
    return serializers.IntegerField(min_value=1, max_value=2**63 - 1, **kwargs)


class StrictInputMixin:
    """Do not silently ignore attempts to write a timestamp, status or FK display."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            writable = {name for name, field in self.fields.items() if not field.read_only}
            unexpected = data.keys() - writable
            if unexpected:
                raise serializers.ValidationError({k: "This field is not accepted." for k in sorted(unexpected)})
        return super().to_internal_value(data)


class PlateField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        # CharField's length validator runs on the canonical result, including
        # any Unicode uppercase expansion, before sending it to varchar(32).
        return normalize_plate(super().to_internal_value(data))


class ParkingSpaceSerializer(StrictInputMixin, serializers.ModelSerializer):
    code = serializers.CharField(max_length=24)
    is_active = serializers.BooleanField(default=True)
    occupied = serializers.BooleanField(read_only=True)
    available = serializers.SerializerMethodField()

    class Meta:
        model = ParkingSpace
        fields = ("id", "code", "is_active", "occupied", "available")
        validators = []  # The DB decides duplicate-code conflicts, also across concurrent requests.

    def get_available(self, obj) -> bool:
        return obj.is_active and not obj.occupied

    def create(self, validated_data):
        return services.create_space(self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        return services.update_space(self.context["request"].user, instance.pk, validated_data)


class VehicleSerializer(StrictInputMixin, serializers.ModelSerializer):
    guest = identifier(source="guest_id")
    guest_name = serializers.CharField(source="guest.full_name", read_only=True)
    plate = PlateField(max_length=32)
    allocated = serializers.BooleanField(read_only=True)

    class Meta:
        model = Vehicle
        fields = ("id", "guest", "guest_name", "plate", "allocated")
        validators = []

    def create(self, validated_data):
        return services.register_vehicle(self.context["request"].user, **validated_data)


class AllocationSerializer(StrictInputMixin, serializers.ModelSerializer):
    space = identifier(source="space_id")
    space_code = serializers.CharField(source="space.code", read_only=True)
    vehicle = identifier(source="vehicle_id")
    vehicle_plate = serializers.CharField(source="vehicle.plate", read_only=True)
    guest = serializers.IntegerField(source="vehicle.guest_id", read_only=True)
    guest_name = serializers.CharField(source="vehicle.guest.full_name", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Allocation
        fields = (
            "id", "space", "space_code", "vehicle", "vehicle_plate", "guest", "guest_name",
            "started_at", "ended_at", "status",
        )
        read_only_fields = ("started_at", "ended_at")
        validators = []  # Active-key decisions require the locked, current state.

    def get_status(self, obj) -> str:
        return "active" if obj.ended_at is None else "released"

    def create(self, validated_data):
        return services.allocate(self.context["request"].user, **validated_data)


class ReleaseRequest(StrictInputMixin, serializers.Serializer):
    """Release has no client-controlled timestamp or association."""


class SearchQuery(serializers.Serializer):
    search = serializers.CharField(max_length=160, required=False, allow_blank=True)


class SpaceQuery(SearchQuery):
    available = serializers.BooleanField(required=False)


class VehicleQuery(SearchQuery):
    guest = identifier(required=False)
    allocated = serializers.BooleanField(required=False)


class AllocationQuery(SearchQuery):
    status = serializers.ChoiceField(choices=("active", "released"), required=False, allow_blank=True)
    space = identifier(required=False)
    vehicle = identifier(required=False)
    guest = identifier(required=False)
