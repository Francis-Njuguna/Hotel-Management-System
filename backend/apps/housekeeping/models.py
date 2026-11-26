from django.conf import settings
from django.db import models
from django.db.models import F, Q


class CleaningStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    INSPECTED = "inspected", "Inspected"


class CleaningTask(models.Model):
    Status = CleaningStatus

    room = models.ForeignKey("lodging.Room", on_delete=models.PROTECT, related_name="cleaning_tasks")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="assigned_cleaning_tasks",
    )
    status = models.CharField(max_length=16, choices=CleaningStatus.choices, default=CleaningStatus.PENDING)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["assignee", "status", "created_at"], name="hk_task_queue_idx"),
            models.Index(fields=["room", "status"], name="hk_task_room_state_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=CleaningStatus.values), name="hk_task_valid_status"),
        ]


class MaintenanceStatus(models.TextChoices):
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class MaintenanceRequest(models.Model):
    Status = MaintenanceStatus

    room = models.ForeignKey("lodging.Room", on_delete=models.PROTECT, related_name="maintenance_requests")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="assigned_maintenance_requests",
    )
    description = models.TextField()
    start = models.DateField()
    end = models.DateField()
    status = models.CharField(max_length=16, choices=MaintenanceStatus.choices, default=MaintenanceStatus.OPEN)
    # Requested intent, retained as history. The effective block is on lodging.RoomClaim.
    blocking = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["room", "status"], name="hk_repair_room_state_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=MaintenanceStatus.values), name="hk_repair_valid_status"),
            models.CheckConstraint(
                condition=(
                    Q(start__lt=F("end"))
                    & models.Func("start", function="isfinite", output_field=models.BooleanField())
                    & models.Func("end", function="isfinite", output_field=models.BooleanField())
                ),
                name="hk_repair_finite_window",
            ),
        ]
