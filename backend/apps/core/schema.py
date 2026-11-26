"""Public shapes of scoped API projections that have no writable model serializer."""
from rest_framework import serializers


class SessionUserSchema(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.ListField(child=serializers.CharField())


class SessionSchema(serializers.Serializer):
    user = SessionUserSchema(allow_null=True)


class LoginInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)


class ResetInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ResetConfirmInput(serializers.Serializer):
    uid = serializers.CharField(max_length=32)
    token = serializers.CharField(max_length=256)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128, trim_whitespace=False)


class DetailSchema(serializers.Serializer):
    detail = serializers.CharField()


class TokenInput(serializers.Serializer):
    token = serializers.CharField(max_length=256)


class AssigneeSchema(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    username = serializers.CharField()


class DashboardSchema(serializers.Serializer):
    date = serializers.DateField()
    metrics = serializers.DictField(help_text='Permission-scoped counts and decimal KES strings.')
    notifications = serializers.ListField(child=serializers.DictField())
    reservations = serializers.ListField(child=serializers.DictField(), required=False)
    tasks = serializers.ListField(child=serializers.DictField(), required=False)
    orders = serializers.ListField(child=serializers.DictField(), required=False)
