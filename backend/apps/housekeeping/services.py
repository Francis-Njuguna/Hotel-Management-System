"""Room work commands. Lock the room before its task/request, never a stay from here."""

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.core.access import can, is_manager
from apps.core.api import Conflict
from apps.core.events import record
from apps.lodging.models import Room, RoomClaim

from .models import CleaningStatus, CleaningTask, MaintenanceRequest, MaintenanceStatus


CLEANER = "Housekeeping Staff"
TECHNICIAN = "Maintenance Staff"


def _visible(queryset, user, capability):
    if not can(user, capability):
        return queryset.none()
    return queryset if is_manager(user) else queryset.filter(assignee_id=user.pk)


def visible_cleaning_tasks(user):
    return _visible(CleaningTask.objects.all(), user, "housekeeping.view")


def visible_maintenance(user):
    return _visible(MaintenanceRequest.objects.all(), user, "maintenance.view")


def _lock_room(room_id):
    try:
        # Serialize readiness/claims with lodging without blocking unrelated FK-only reads.
        return Room.objects.select_for_update(no_key=True).get(pk=room_id)
    except Room.DoesNotExist as exc:
        raise ValidationError({"room": "Choose an existing room."}) from exc


def _lock_work(work):
    # The owning room is immutable in the API. Don't lock through a nullable assignee join.
    room = _lock_room(work.room_id)
    model = type(work)
    try:
        work = model.objects.select_for_update().get(pk=work.pk, room_id=room.pk)
    except model.DoesNotExist as exc:
        raise NotFound() from exc
    return room, work


def _lock_accounts(user, assignee_id=None):
    # Staff administration takes the User lock before changing activation or groups.
    # Reload both accounts (no cached permissions), in one consistent PK order.
    user_id = getattr(user, "pk", None)
    if user_id is None:
        raise PermissionDenied()
    ids = {user_id}
    if assignee_id is not None:
        ids.add(assignee_id)
    staff = get_user_model().objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk")
    accounts = {account.pk: account for account in staff}
    actor = accounts.get(user_id)
    if actor is None or not actor.is_active:
        raise PermissionDenied()
    return actor, accounts.get(assignee_id)


def _require_manager(user, capability):
    if not can(user, capability) or not is_manager(user):
        raise PermissionDenied("This action requires a manager.")


def _require_worker(actor, work, capability):
    if not can(actor, capability):
        raise PermissionDenied()
    if work.assignee_id != actor.pk and not is_manager(actor):
        # Also check after acquiring the lock: the original scoped lookup isn't a grant.
        raise NotFound()


def _eligible(account, role, capability):
    if not can(account, capability) or not account.groups.filter(name=role).exists():
        raise ValidationError({"assignee": f"Choose an active member of {role}."})
    return account


def _dispatch_context(user, room_id, assignee_id, domain, role):
    # Reject an unauthorized dispatch without looking up the room or locking anyone
    # selected by the caller. Then recheck grants/assignment under the account locks.
    manage = f"{domain}.manage"
    _require_manager(user, manage)
    room = _lock_room(room_id)
    actor, assignee = _lock_accounts(user, assignee_id)
    _require_manager(actor, manage)
    if assignee_id is not None:
        _eligible(assignee, role, f"{domain}.work")
    return room, actor, assignee


def _local_day():
    return timezone.localdate(timezone=timezone.get_default_timezone())


def _occupied(room):
    # Overdue guests remain occupants. Neither the planned dates nor blocking bit decides this.
    return RoomClaim.objects.filter(room=room, reservation__status="checked_in").exists()


def _set_cleanliness(room, value):
    if room.cleanliness != value:
        room.cleanliness = value
        room.save(update_fields=["cleanliness"])


def _new_task(room, assignee, notes):
    _set_cleanliness(room, "dirty")
    return CleaningTask.objects.create(
        room=room, assignee=assignee, notes=notes,
        status=CleaningStatus.ASSIGNED if assignee else CleaningStatus.PENDING,
    )


@transaction.atomic
def turnover(room, user):
    """Checkout calls this once per room in its enclosing transaction, even if other work exists."""
    locked_room = _lock_room(room.pk)
    actor, _ = _lock_accounts(user)
    # Checkout is a front-desk command, not a housekeeping dispatch permission.
    if not can(actor, "reservations.manage"):
        raise PermissionDenied()
    task = _new_task(locked_room, None, "")
    record(actor, "housekeeping.turnover", task, "Checkout opened a pending turnover task; room marked dirty.")
    return task


@transaction.atomic
def create_cleaning_task(user, *, room_id, notes="", assignee_id=None):
    room, actor, assignee = _dispatch_context(user, room_id, assignee_id, "housekeeping", CLEANER)
    task = _new_task(room, assignee, notes)
    record(actor, "housekeeping.created", task, f"Cleaning task opened as {task.status}; room marked dirty.")
    return task


_NEXT_CLEANING_STATUS = {
    CleaningStatus.PENDING: CleaningStatus.ASSIGNED,
    CleaningStatus.ASSIGNED: CleaningStatus.IN_PROGRESS,
    CleaningStatus.IN_PROGRESS: CleaningStatus.COMPLETED,
    CleaningStatus.COMPLETED: CleaningStatus.INSPECTED,
}


@transaction.atomic
def transition_cleaning_task(task, user, *, status, assignee_id=None):
    manager_only = status in (CleaningStatus.ASSIGNED, CleaningStatus.INSPECTED) or assignee_id is not None
    if manager_only:
        _require_manager(user, "housekeeping.manage")
    if assignee_id is not None and status != CleaningStatus.ASSIGNED:
        raise ValidationError({"assignee": "Select a housekeeper only when assigning this task."})
    room, task = _lock_work(task)
    actor, candidate = _lock_accounts(user, assignee_id)
    _require_worker(actor, task, "housekeeping.work")
    if manager_only:
        _require_manager(actor, "housekeeping.manage")
    if task.status not in _NEXT_CLEANING_STATUS or _NEXT_CLEANING_STATUS[task.status] != status:
        raise Conflict(f"Cannot move a {task.status} cleaning task to {status}.")

    fields = ["status"]
    if status == CleaningStatus.ASSIGNED:
        task.assignee = _eligible(candidate, CLEANER, "housekeeping.work")
        fields.append("assignee")

    cleanliness = "dirty"
    if status == CleaningStatus.INSPECTED:
        today = _local_day()
        if _occupied(room):
            raise Conflict("Cannot inspect this room for release while it is occupied.")
        if RoomClaim.objects.filter(
            room=room, maintenance__isnull=False, blocking=True, start__lte=today, end__gt=today,
        ).exists():
            raise Conflict("Resolve the current maintenance block before inspection.")
        # All task creation/transitions for this room take its lock, including checkout.
        others = CleaningTask.objects.filter(room=room).exclude(pk=task.pk)
        if not others.exclude(status=CleaningStatus.INSPECTED).exists():
            cleanliness = "inspected"

    task.status = status
    task.save(update_fields=fields)
    _set_cleanliness(room, cleanliness)
    record(actor, f"housekeeping.{status}", task, f"Cleaning task marked {status}; room cleanliness: {cleanliness}.")
    return task


@transaction.atomic
def open_maintenance(user, *, room_id, description, start, end, blocking, assignee_id=None):
    room, actor, assignee = _dispatch_context(user, room_id, assignee_id, "maintenance", TECHNICIAN)
    for field, day in (("start", start), ("end", end)):
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValidationError({field: "Provide a local calendar date."})
    if start >= end:
        raise ValidationError({"end": "The end date must be after the start date."})
    if not isinstance(description, str) or not description.strip():
        raise ValidationError({"description": "Describe the repair."})
    if not isinstance(blocking, bool):
        raise ValidationError({"blocking": "Specify whether to take these nights out of inventory."})
    if blocking and start <= _local_day() < end and _occupied(room):
        raise Conflict("Cannot take a currently occupied room out of inventory.")

    work = MaintenanceRequest.objects.create(
        room=room, assignee=assignee, description=description, start=start, end=end, blocking=blocking,
    )
    if blocking:
        # The same PostgreSQL exclusion constraint as bookings is the final arbiter. If
        # the insert fails, let the exception unwind this entire command (including work).
        try:
            RoomClaim.objects.create(
                room=room, maintenance=work, start=start, end=end, blocking=True, nightly_rate=Decimal("0.00"),
            )
        except IntegrityError as exc:
            if getattr(exc.__cause__, "sqlstate", None) != "23P01":  # exclusion_violation
                raise
            raise Conflict("This room already has a commitment in that date range.") from exc
    record(actor, "maintenance.opened", work, "Opened blocking maintenance." if blocking else "Opened nonblocking maintenance.")
    return work


@transaction.atomic
def resolve_maintenance(work, user):
    room, work = _lock_work(work)
    actor, _ = _lock_accounts(user)
    _require_worker(actor, work, "maintenance.work")
    if work.status != MaintenanceStatus.OPEN:
        raise Conflict("This maintenance request is already resolved.")
    if work.blocking:
        released = RoomClaim.objects.filter(
            maintenance=work, room=room, start=work.start, end=work.end, blocking=True,
        ).update(blocking=False)
        if released != 1:
            raise Conflict("The calendar block does not match this work request; review it before resolution.")
    # Retain the requested window/blocking intent and claim history. Never change
    # cleanliness, another work order's block, or a guest's room commitment here.
    work.status = MaintenanceStatus.RESOLVED
    work.save(update_fields=["status"])
    record(actor, "maintenance.resolved", work, "Maintenance resolved.")
    return work
