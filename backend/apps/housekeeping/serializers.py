from collections.abc import Mapping

from rest_framework import serializers

from .models import CleaningStatus, CleaningTask, MaintenanceRequest, MaintenanceStatus


ROOM_ID_MAX = 2**63 - 1
USER_ID_MAX = 2**31 - 1


class RoomWorkSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True)
    assignee_name = serializers.SerializerMethodField()

    def get_assignee_name(self, obj) -> str | None:
        if obj.assignee_id is None:
            return None
        return obj.assignee.get_full_name() or obj.assignee.get_username()


class CleaningTaskSerializer(RoomWorkSerializer):
    class Meta:
        model = CleaningTask
        fields = ("id", "room", "room_number", "assignee", "assignee_name", "status", "notes", "created_at")
        read_only_fields = fields


class MaintenanceRequestSerializer(RoomWorkSerializer):
    class Meta:
        model = MaintenanceRequest
        fields = (
            "id", "room", "room_number", "assignee", "assignee_name", "status", "description",
            "start", "end", "blocking", "created_at",
        )
        read_only_fields = fields


class CommandSerializer(serializers.Serializer):
    """Reject, rather than silently ignoring, attempts to send extra workflow fields."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            extra = data.keys() - self.fields.keys()
            if extra:
                raise serializers.ValidationError({name: "Not accepted by this command." for name in sorted(extra)})
        return super().to_internal_value(data)


class NewRoomWorkSerializer(CommandSerializer):
    # Pass identifiers to the service, which resolves them inside the transaction/locks.
    room = serializers.IntegerField(source="room_id", min_value=1, max_value=ROOM_ID_MAX)
    assignee = serializers.IntegerField(
        source="assignee_id", min_value=1, max_value=USER_ID_MAX, required=False, allow_null=True,
    )


class CreateCleaningTaskSerializer(NewRoomWorkSerializer):
    notes = serializers.CharField(allow_blank=True, required=False)


class TransitionCleaningTaskSerializer(CommandSerializer):
    status = serializers.ChoiceField(choices=CleaningStatus.choices)
    assignee = serializers.IntegerField(source="assignee_id", min_value=1, max_value=USER_ID_MAX, required=False)


class OpenMaintenanceSerializer(NewRoomWorkSerializer):
    description = serializers.CharField()
    start = serializers.DateField()
    end = serializers.DateField()
    blocking = serializers.BooleanField()


class ResolveMaintenanceSerializer(CommandSerializer):
    pass  # An empty command; the server owns all changes.


class WorkFilters(serializers.Serializer):
    room = serializers.IntegerField(source="room_id", min_value=1, max_value=ROOM_ID_MAX, required=False)
    assignee = serializers.IntegerField(source="assignee_id", min_value=1, max_value=USER_ID_MAX, required=False)


class CleaningFilters(WorkFilters):
    status = serializers.ChoiceField(choices=CleaningStatus.choices, required=False)


class MaintenanceFilters(WorkFilters):
    status = serializers.ChoiceField(choices=MaintenanceStatus.choices, required=False)
    blocking = serializers.BooleanField(required=False)
