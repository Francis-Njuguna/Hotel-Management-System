from collections.abc import Mapping
from decimal import Decimal

from rest_framework import serializers

from apps.core.images import SafeImageField

from .models import ZERO, MenuItem, Order, OrderItem, OrderStatus


class StrictInput:
    """Reject, rather than silently discard, fields outside this command."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            writable = {name for name, field in self.fields.items() if not field.read_only}
            if data.keys() - writable:
                raise serializers.ValidationError({"non_field_errors": ["Unexpected or read-only field."]})
            if self.partial and not data:
                raise serializers.ValidationError({"non_field_errors": ["Provide at least one field to change."]})
        return super().to_internal_value(data)


class PriceField(serializers.DecimalField):
    def to_internal_value(self, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            raise serializers.ValidationError("Use an exact KES amount, for example '120.50'.")
        return super().to_internal_value(value)


class MenuItemSerializer(StrictInput, serializers.ModelSerializer):
    image = SafeImageField(required=False, allow_null=True)
    price = PriceField(max_digits=12, decimal_places=2, min_value=ZERO, coerce_to_string=True)
    available = serializers.BooleanField(default=True)

    class Meta:
        model = MenuItem
        fields = ["id", "name", "category", "price", "available", "image", "description"]
        read_only_fields = ["id"]

    def validate_image(self, value):
        return "" if value is None else value


class WholeNumber(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int and not (isinstance(data, str) and data.isascii() and data.isdigit()):
            raise serializers.ValidationError("Use a positive whole number.")
        return super().to_internal_value(data)


class DomainID(WholeNumber):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=2**63 - 1, **kwargs)


class StaffID(WholeNumber):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=2**31 - 1, allow_null=True, **kwargs)


class SelectedItemInput(StrictInput, serializers.Serializer):
    menu_item = DomainID()
    quantity = WholeNumber(min_value=1, max_value=2**31 - 1)


class OrderCreateInput(StrictInput, serializers.Serializer):
    reservation = DomainID(required=False, allow_null=True)
    room = DomainID(required=False, allow_null=True)
    assignee = StaffID(required=False)
    items = SelectedItemInput(many=True, allow_empty=False)

    def validate_items(self, items):
        if len({line["menu_item"] for line in items}) != len(items):
            raise serializers.ValidationError("Specify each menu item once and use its quantity.")
        return items

    def validate(self, attrs):
        if attrs.get("room") is not None and attrs.get("reservation") is None:
            raise serializers.ValidationError({"room": "Select a checked-in stay for room service."})
        return attrs


class AssignmentInput(StrictInput, serializers.Serializer):
    assignee = StaffID()


class TransitionInput(StrictInput, serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    assignee = StaffID(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Specify a target status or an assignee.")
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)

    class Meta:
        model = OrderItem
        fields = ["id", "menu_item", "menu_item_name", "quantity", "unit_price"]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    guest = serializers.IntegerField(source="guest_id", read_only=True, allow_null=True)
    room_number = serializers.CharField(source="room.number", read_only=True, allow_null=True)
    assignee_name = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "reservation", "room", "room_number", "guest", "assignee", "assignee_name",
                  "status", "created_at", "items", "total"]
        read_only_fields = fields

    def get_assignee_name(self, order) -> str | None:
        if order.assignee_id is None:
            return None
        return order.assignee.get_full_name() or order.assignee.username

    def get_total(self, order) -> str:
        return format(order.total, ".2f")


class StayRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    number = serializers.CharField(read_only=True)


class OrderStaySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    rooms = StayRoomSerializer(many=True, read_only=True)
