"""Parking commands. All acceptance checks, writes and audit share one commit."""

from contextlib import contextmanager

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.api import Conflict
from apps.core.events import record
from apps.lodging.models import Guest

from .models import Allocation, ParkingSpace, Vehicle


SPACE_TAKEN = "This space already has an active allocation."
VEHICLE_PARKED = "This vehicle already has an active allocation."
_CONFLICTS = {
    "parking_space_code_unique": "This space code is already registered.",
    "parking_vehicle_plate_unique": "This plate is already registered.",
    "parking_one_active_per_space": SPACE_TAKEN,
    "parking_one_active_per_vehicle": VEHICLE_PARKED,
    "parking_allocation_time_order": "Release time cannot precede the allocation start.",
}


@contextmanager
def _command():
    try:
        with transaction.atomic():
            yield
    except IntegrityError as exc:
        # Translate known PostgreSQL constraints *after* rolling back the
        # transaction/savepoint. Never expose the failing SQL or key value.
        name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if name in _CONFLICTS:
            raise Conflict(_CONFLICTS[name]) from None
        if name == "parking_space_code_nonblank":
            raise ValidationError({"code": "Enter a nonblank space code."}) from None
        if name == "parking_vehicle_plate_canonical":
            raise ValidationError({"plate": "Enter a valid nonblank registration plate."}) from None
        raise


def create_space(actor, *, code, is_active=True):
    with _command():
        space = ParkingSpace.objects.create(code=code, is_active=is_active)
        space.occupied = False  # New row is not yet visible to any allocator.
        record(actor, "parking.space_created", space, "Parking space created.")
        return space


def update_space(actor, space_id, changes):
    with _command():
        space = get_object_or_404(ParkingSpace.objects.select_for_update(), pk=space_id)
        # A separate statement after the space lock sees any intervening allocation.
        space.occupied = Allocation.objects.filter(space=space, ended_at__isnull=True).exists()
        if changes.get("is_active") is False and space.occupied:
            raise Conflict("Release the active allocation before deactivating this space.")
        changed = []
        for field in ("code", "is_active"):
            if field in changes and changes[field] != getattr(space, field):
                setattr(space, field, changes[field])
                changed.append(field)
        if changed:
            space.save(update_fields=changed)
            record(actor, "parking.space_updated", space, "Parking space updated.")
        return space


def register_vehicle(actor, *, guest_id, plate):
    with _command():
        try:
            guest = Guest.objects.select_for_update().only("id", "full_name").get(pk=guest_id)
        except Guest.DoesNotExist:
            raise ValidationError({"guest": "Select a registered guest."}) from None
        vehicle = Vehicle.objects.create(guest=guest, plate=plate)
        vehicle.allocated = False
        record(actor, "parking.vehicle_registered", vehicle, "Guest vehicle registered.")
        return vehicle


def _lock_parents(space_id, vehicle_id):
    # All allocation/release commands use this order, including first inserts
    # when there is no Allocation row to lock. Guest is display data, not a lock.
    try:
        space = ParkingSpace.objects.select_for_update().get(pk=space_id)
    except ParkingSpace.DoesNotExist:
        raise ValidationError({"space": "Select a registered parking space."}) from None
    try:
        vehicle = (
            Vehicle.objects.select_for_update(of=("self",))
            .select_related("guest")
            .only("plate", "guest__full_name")
            .get(pk=vehicle_id)
        )
    except Vehicle.DoesNotExist:
        raise ValidationError({"vehicle": "Select a registered vehicle."}) from None
    return space, vehicle


def allocate(actor, *, space_id, vehicle_id):
    with _command():
        space, vehicle = _lock_parents(space_id, vehicle_id)
        if not space.is_active:
            raise Conflict("An inactive space cannot receive a vehicle.")
        active = Allocation.objects.filter(ended_at__isnull=True)
        if active.filter(space=space).exists():
            raise Conflict(SPACE_TAKEN)
        if active.filter(vehicle=vehicle).exists():
            raise Conflict(VEHICLE_PARKED)
        allocation = Allocation.objects.create(space=space, vehicle=vehicle)
        record(actor, "parking.allocated", allocation, "Parking allocation started.")
        return allocation


def release(actor, allocation):
    with _command():
        # Read immutable ownership to find the parents; only inspect workflow
        # state on the re-read allocation after acquiring all three locks.
        space, vehicle = _lock_parents(allocation.space_id, allocation.vehicle_id)
        current = get_object_or_404(Allocation.objects.select_for_update(), pk=allocation.pk)
        if (current.space_id, current.vehicle_id) != (space.pk, vehicle.pk):
            raise Conflict("The allocation association changed. Reload the allocation.")
        if current.ended_at is not None:
            raise Conflict("This allocation has already been released.")
        current.ended_at = timezone.now()
        current.save(update_fields=["ended_at"])
        record(actor, "parking.released", current, "Parking allocation released.")
        # Use the locked parents for the response; do not re-fetch them after commit.
        current.space, current.vehicle = space, vehicle
        return current
