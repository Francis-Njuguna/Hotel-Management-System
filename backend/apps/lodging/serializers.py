import json
from collections.abc import Mapping
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.images import SafeImageField

from .models import Cleanliness, Guest, Reservation, ReservationEvent, ReservationStatus, Room, RoomCategory, RoomClaim, validate_facilities
from .services import validate_interval


class StrictInput:
    """A status/total/cleanliness in the wrong command is an error, not a silent no-op."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            writable = {name for name, field in self.fields.items() if not field.read_only}
            extra = data.keys() - writable
            if extra:
                raise serializers.ValidationError({str(key): "This field cannot be set here." for key in extra})
            if self.partial and not data:
                raise serializers.ValidationError({"non_field_errors": ["Provide at least one field to change."]})
        return super().to_internal_value(data)


class GuestSerializer(StrictInput, serializers.ModelSerializer):
    reference = serializers.CharField(max_length=64, allow_blank=True, required=False)
    email = serializers.EmailField(max_length=254, allow_blank=True, required=False)

    class Meta:
        model = Guest
        fields = ["id", "reference", "full_name", "email", "phone", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_email(self, value):
        return value.strip().lower()


@extend_schema_field(serializers.ListField(child=serializers.CharField()))
class FacilitiesField(serializers.Field):
    """Accept JSON arrays, or FormData with a JSON array/individual repeated entries."""

    def get_value(self, data):
        if hasattr(data, "getlist") and self.field_name in data:
            values = data.getlist(self.field_name)
            if len(values) == 1 and isinstance(values[0], str) and values[0].lstrip().startswith(("[", "{")):
                return values[0]
            return values
        return super().get_value(data)

    def to_internal_value(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, RecursionError) as exc:
                raise serializers.ValidationError("Facilities must be a JSON list of names.") from exc
        try:
            validate_facilities(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return [item.strip() for item in value]

    def to_representation(self, value):
        return value


class RoomRateField(serializers.DecimalField):
    def to_internal_value(self, value):
        if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
            raise serializers.ValidationError("Use an exact KES amount, e.g. '1200.50'.")
        return super().to_internal_value(value)


class RoomSerializer(StrictInput, serializers.ModelSerializer):
    image = SafeImageField(required=False, allow_null=True)
    facilities = FacilitiesField(required=False)
    nightly_rate = RoomRateField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"), coerce_to_string=True)
    capacity = serializers.IntegerField(min_value=1, max_value=2**31 - 1)
    is_active = serializers.BooleanField(default=True)
    occupied = serializers.BooleanField(read_only=True)
    maintenance = serializers.BooleanField(read_only=True)

    class Meta:
        model = Room
        fields = ["id", "number", "category", "nightly_rate", "capacity", "description", "facilities", "image",
                  "cleanliness", "is_active", "occupied", "maintenance"]
        read_only_fields = ["id", "cleanliness"]


class RoomFilters(serializers.Serializer):
    category = serializers.ChoiceField(choices=RoomCategory.choices, required=False)
    cleanliness = serializers.ChoiceField(choices=Cleanliness.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    occupied = serializers.BooleanField(required=False)
    maintenance = serializers.BooleanField(required=False)


class AvailabilityInterval(serializers.Serializer):
    arrival = serializers.DateField()
    departure = serializers.DateField()

    def validate(self, attrs):
        validate_interval(attrs["arrival"], attrs["departure"])
        return attrs


class RoomIDField(serializers.IntegerField):
    def to_internal_value(self, data):
        # In JSON a boolean, string or floating point number is not an integer ID.
        if type(data) is not int:
            raise serializers.ValidationError("Room IDs must be integers.")
        return super().to_internal_value(data)


class ReservationInput(StrictInput, serializers.Serializer):
    guest = serializers.PrimaryKeyRelatedField(
        queryset=Guest.objects.all(), pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    )
    arrival = serializers.DateField()
    departure = serializers.DateField()
    room_ids = serializers.ListField(child=RoomIDField(min_value=1, max_value=2**63 - 1), allow_empty=False)
    confirm = serializers.BooleanField(default=True)

    def validate_room_ids(self, ids):
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Select each room only once.")
        return ids

    def validate(self, attrs):
        if "arrival" in attrs and "departure" in attrs:
            validate_interval(attrs["arrival"], attrs["departure"])
        return attrs


class ReservationFilters(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReservationStatus.choices, required=False)
    guest = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)
    room = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)
    arrival = serializers.DateField(required=False)
    departure = serializers.DateField(required=False)


class BookedRoomSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="room_id", read_only=True)
    number = serializers.CharField(source="room.number", read_only=True)
    nightly_rate = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)

    class Meta:
        model = RoomClaim
        fields = ["id", "number", "nightly_rate"]
        read_only_fields = fields


class ReservationEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = ReservationEvent
        fields = ["id", "actor", "actor_name", "status", "note", "created_at"]
        read_only_fields = fields


class ReservationSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source="guest.full_name", read_only=True)
    rooms = BookedRoomSerializer(source="claims", many=True, read_only=True)

    class Meta:
        model = Reservation
        fields = ["id", "guest", "guest_name", "arrival", "departure", "status", "checked_in_at", "checked_out_at", "created_at", "rooms"]
        read_only_fields = fields


class ReservationDetailSerializer(ReservationSerializer):
    events = ReservationEventSerializer(many=True, read_only=True)

    class Meta(ReservationSerializer.Meta):
        fields = [*ReservationSerializer.Meta.fields, "events"]
        read_only_fields = fields


class StayCommand(StrictInput, serializers.Serializer):
    """The action URL selects the workflow. No client-supplied actual time, status or money."""


class GuestVisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = ["id", "arrival", "departure", "status", "checked_in_at", "checked_out_at"]
        read_only_fields = fields


class GuestPaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    invoice = serializers.IntegerField(source="invoice_id", read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    receipt_number = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class GuestHistorySerializer(serializers.Serializer):
    reservations = GuestVisitSerializer(many=True, read_only=True)
    payments = GuestPaymentSerializer(many=True, read_only=True, required=False)
