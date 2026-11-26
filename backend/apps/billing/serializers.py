from collections.abc import Mapping
from decimal import Decimal

from rest_framework import serializers

from .models import CENT, TOTAL_DIGITS, ZERO, Invoice, InvoiceItem, Payment, PaymentMethod


class PaymentSerializer(serializers.ModelSerializer):
    receipt_number = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True, read_only=True)

    class Meta:
        model = Payment
        fields = ("id", "invoice", "receipt_number", "amount", "method", "reference", "received_by", "created_at")
        read_only_fields = fields


class InvoiceItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True, read_only=True)
    line_total = serializers.DecimalField(max_digits=TOTAL_DIGITS, decimal_places=2, coerce_to_string=True, read_only=True)

    class Meta:
        model = InvoiceItem
        fields = ("id", "invoice", "description", "quantity", "unit_price", "line_total", "source_key", "created_at")
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    total = serializers.DecimalField(max_digits=TOTAL_DIGITS, decimal_places=2, coerce_to_string=True, read_only=True)
    paid = serializers.DecimalField(max_digits=TOTAL_DIGITS, decimal_places=2, coerce_to_string=True, read_only=True)
    balance = serializers.DecimalField(max_digits=TOTAL_DIGITS, decimal_places=2, coerce_to_string=True, read_only=True)

    class Meta:
        model = Invoice
        fields = ("id", "reservation", "created_at", "closed_at", "status", "total", "paid", "balance")
        read_only_fields = fields


class InvoiceDetailSerializer(InvoiceSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta(InvoiceSerializer.Meta):
        fields = (*InvoiceSerializer.Meta.fields, "items", "payments")
        read_only_fields = fields


class CommandSerializer(serializers.Serializer):
    """Fail rather than silently accept invented totals, receivers, timestamps or states."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected = data.keys() - self.fields.keys()
            if unexpected:
                raise serializers.ValidationError({name: "Unexpected field." for name in unexpected})
        return super().to_internal_value(data)


class MoneyInput(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=12, decimal_places=2, **kwargs)

    def to_internal_value(self, data):
        # DRF normally converts floats to strings. By that point precision may already
        # be lost. Accept decimal strings, Decimals, or exact whole-number JSON integers.
        if not isinstance(data, (str, int, Decimal)) or isinstance(data, bool):
            raise serializers.ValidationError("Use a KES decimal string, not a floating-point value.")
        return super().to_internal_value(data)


class QuantityInput(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int and not (isinstance(data, str) and data.strip().isascii() and data.strip().isdigit()):
            raise serializers.ValidationError("Use a positive whole-number quantity.")
        return super().to_internal_value(data)


class TextInput(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Enter text.")
        return super().to_internal_value(data)


class ChargeCommand(CommandSerializer):
    description = TextInput()
    quantity = QuantityInput(min_value=1, max_value=2147483647)
    unit_price = MoneyInput(min_value=ZERO)
    reference = TextInput(max_length=128)


class PaymentCommand(CommandSerializer):
    amount = MoneyInput(min_value=CENT)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = TextInput(max_length=128, help_text="Original till voucher or verified external transaction reference.")


class InvoiceFilters(serializers.Serializer):
    reservation = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False,
                                          help_text="Exact reservation ID. Required for reception folio lookups.")
    status = serializers.ChoiceField(choices=("open", "closed"), required=False)


class PaymentFilters(InvoiceFilters):
    invoice = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)
    method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
