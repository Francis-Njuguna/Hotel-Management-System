"""Atomic lodging commands. Mutating services and their API actions check the grant.

Owning-row locks: reservation → existing folio → affected orders → sorted rooms.
Children are changed only under their owner's lock. A new row is private to the
creating transaction; the database exclusion also protects against direct writes.
"""

from contextlib import contextmanager
from datetime import date, datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404

from apps.core.api import Conflict

from . import selectors
from .models import Cleanliness, Guest, Reservation, ReservationEvent, ReservationStatus as Status, Room, RoomClaim, ROOM_EXCLUSION


def _record(user, verb, instance, summary):
    from apps.core.events import record

    record(user, verb, instance, summary)


def _event(reservation, user, verb, summary, note=None):
    ReservationEvent.objects.create(reservation=reservation, actor=user, status=reservation.status, note=note or summary)
    _record(user, verb, reservation, summary)


@contextmanager
def _write(user, capability="reservations.manage", *, catalog=None):
    from apps.core.access import can

    if not can(user, capability):
        raise PermissionDenied()
    try:
        with transaction.atomic():
            yield
    except IntegrityError as exc:
        # Only translate known business conflicts, and only *after* rollback.
        cause = exc.__cause__
        diag = getattr(cause, "diag", None)
        if getattr(diag, "constraint_name", None) == ROOM_EXCLUSION:
            raise Conflict("One or more rooms are already committed for these nights.") from exc
        if catalog and getattr(cause, "sqlstate", None) == "23505" and getattr(diag, "table_name", None) == catalog._meta.db_table:
            detail = "This guest reference or email is already registered." if catalog is Guest else "This room number is already registered."
            raise Conflict(detail) from exc
        raise


def _apply(instance, data, allowed):
    unknown = data.keys() - allowed
    if unknown:
        raise ValidationError({key: "This field cannot be set here." for key in unknown})
    for field, value in data.items():
        setattr(instance, field, value)
    instance.save()


def save_guest(user, data, *, pk=None):
    with _write(user, "guests.manage", catalog=Guest):
        guest = Guest() if pk is None else get_object_or_404(Guest.objects.select_for_update(), pk=pk)
        if pk is not None and "reference" in data and not data["reference"].strip():
            raise ValidationError({"reference": "An existing guest reference must not be blank."})
        _apply(guest, data, {"reference", "full_name", "email", "phone"})
        _record(user, "guest.create" if pk is None else "guest.update", guest, "Guest profile registered." if pk is None else "Guest profile updated.")
        return guest


def save_room(user, data, *, pk=None):
    # Validation (including bounded raster decoding) occurs before taking this lock.
    # Updating the catalog and a checkout/inspection must never overwrite each other.
    with _write(user, "rooms.manage", catalog=Room):
        room = Room() if pk is None else get_object_or_404(Room.objects.select_for_update(), pk=pk)
        old_image = room.image.name if room.image else None
        _apply(room, data, {"number", "category", "capacity", "nightly_rate", "facilities", "image", "description", "is_active"})
        _record(user, "room.create" if pk is None else "room.update", room, "Room registered." if pk is None else "Room catalog updated.")
        if old_image and old_image != room.image.name:
            transaction.on_commit(lambda: _prune_image(old_image), robust=True)
        return room


def _prune_image(key):
    # Protect any other catalog entry that legitimately shares an existing storage key.
    if not Room.objects.filter(image=key).exists():
        Room._meta.get_field("image").storage.delete(key)


def validate_interval(arrival, departure):
    if not isinstance(arrival, date) or isinstance(arrival, datetime):
        raise ValidationError({"arrival": "Provide a local arrival date."})
    if not isinstance(departure, date) or isinstance(departure, datetime):
        raise ValidationError({"departure": "Provide a local departure date."})
    if departure <= arrival:
        raise ValidationError({"departure": "Departure must be later than arrival."})


def _room_ids(ids):
    if not isinstance(ids, (tuple, list)) or not ids:
        raise ValidationError({"room_ids": "Select at least one room."})
    if any(type(pk) is not int or not 0 < pk <= 2**63 - 1 for pk in ids):
        raise ValidationError({"room_ids": "Room IDs must be positive integers."})
    if len(set(ids)) != len(ids):
        raise ValidationError({"room_ids": "Select each room only once."})
    return set(ids)


def _lock_reservation(pk):
    return get_object_or_404(Reservation.objects.select_for_update(), pk=pk)


def _lock_rooms(ids):
    # ORDER BY is on the SQL that takes the locks, not just on the Python IN-list.
    rooms = {room.pk: room for room in Room.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if rooms.keys() != ids:
        raise ValidationError({"room_ids": "One or more selected rooms do not exist."})
    return rooms


def _booking_claims(reservation):
    claims = {c.room_id: c for c in RoomClaim.objects.filter(reservation=reservation).order_by("room_id")}
    if not claims:
        raise Conflict("This reservation has no assigned rooms.")
    return claims


def _check_sale(reservation, rooms, ids, arrival, departure, *, blocking):
    validate_interval(arrival, departure)
    if departure <= selectors.business_date():
        raise Conflict("This booking interval has already ended.")
    if any(not rooms[pk].is_active for pk in ids):
        raise Conflict("One or more selected rooms are inactive.")
    if blocking:
        conflicts = selectors.overlapping_claims(arrival, departure).filter(room_id__in=ids)
        if reservation is not None:
            conflicts = conflicts.exclude(reservation_id=reservation.pk)
        if conflicts.exists():
            raise Conflict("One or more rooms are already committed for these nights.")


def _change_claims(reservation, old, rooms, ids, *, blocking):
    # Keep a retained room's original claim ID and agreed price, even when dates
    # change or the catalog was repriced. Only newly selected rooms get today's rate.
    removed = old.keys() - ids
    kept = old.keys() & ids
    if removed:
        RoomClaim.objects.filter(reservation=reservation, room_id__in=removed).delete()
    if kept:
        RoomClaim.objects.filter(reservation=reservation, room_id__in=kept).update(
            start=reservation.arrival, end=reservation.departure, blocking=blocking
        )
    RoomClaim.objects.bulk_create([
        RoomClaim(room=rooms[pk], reservation=reservation, start=reservation.arrival, end=reservation.departure,
                  blocking=blocking, nightly_rate=rooms[pk].nightly_rate)
        for pk in sorted(ids - old.keys())
    ])


def _plan(arrival, departure, ids):
    return f"{arrival.isoformat()} to {departure.isoformat()}, room IDs {', '.join(str(pk) for pk in sorted(ids))}"


def create_reservation(user, *, guest, arrival, departure, room_ids, confirm=True):
    ids = _room_ids(room_ids)
    validate_interval(arrival, departure)
    with _write(user):
        # The new header is private; on any competing room or a failed audit it,
        # every claim and the event are rolled back. A pending request is not a hold.
        reservation = Reservation.objects.create(
            guest=guest, arrival=arrival, departure=departure, status=Status.CONFIRMED if confirm else Status.PENDING
        )
        rooms = _lock_rooms(ids)
        _check_sale(reservation, rooms, ids, arrival, departure, blocking=confirm)
        _change_claims(reservation, {}, rooms, ids, blocking=confirm)
        _event(reservation, user, "reservation.create", "Reservation created.", f"Created {reservation.status}: {_plan(arrival, departure, ids)}.")
        return reservation


def amend_reservation(pk, user, *, guest=None, arrival=None, departure=None, room_ids=None, confirm=None):
    with _write(user):
        reservation = _lock_reservation(pk)
        if reservation.status not in (Status.PENDING, Status.CONFIRMED):
            raise Conflict("Only pending or confirmed reservations can be amended.")
        if reservation.status == Status.CONFIRMED and confirm is False:
            raise Conflict("A confirmed reservation cannot be changed to pending. Use cancellation to release it.")
        old = _booking_claims(reservation)
        ids = set(old) if room_ids is None else _room_ids(room_ids)
        rooms = _lock_rooms(ids | old.keys())
        today = selectors.business_date()
        if reservation.arrival < today:
            raise Conflict("The scheduled arrival date has passed; this booking cannot be amended.")
        if arrival is not None and arrival < today:
            raise ValidationError({"arrival": "An amendment cannot move arrival into the past."})
        old_plan = _plan(reservation.arrival, reservation.departure, old)
        reservation.arrival = arrival if arrival is not None else reservation.arrival
        reservation.departure = departure if departure is not None else reservation.departure
        if guest is not None:
            reservation.guest = guest
        blocking = reservation.status == Status.CONFIRMED or confirm is True
        _check_sale(reservation, rooms, ids, reservation.arrival, reservation.departure, blocking=blocking)
        _change_claims(reservation, old, rooms, ids, blocking=blocking)
        reservation.status = Status.CONFIRMED if blocking else Status.PENDING
        reservation.save(update_fields=["guest", "arrival", "departure", "status"])
        new_plan = _plan(reservation.arrival, reservation.departure, ids)
        _event(reservation, user, "reservation.amend", "Reservation amended.", f"Amended booking: {old_plan} → {new_plan}.")
        return reservation


def confirm(pk, user):
    with _write(user):
        reservation = _lock_reservation(pk)
        if reservation.status != Status.PENDING:
            raise Conflict("Only a pending reservation can be confirmed.")
        old = _booking_claims(reservation)
        ids = set(old)
        rooms = _lock_rooms(ids)
        _check_sale(reservation, rooms, ids, reservation.arrival, reservation.departure, blocking=True)
        _change_claims(reservation, old, rooms, ids, blocking=True)
        reservation.status = Status.CONFIRMED
        reservation.save(update_fields=["status"])
        _event(reservation, user, "reservation.confirm", "All rooms confirmed.")
        return reservation


def cancel(pk, user):
    with _write(user):
        reservation = _lock_reservation(pk)
        if reservation.status not in (Status.PENDING, Status.CONFIRMED):
            raise Conflict("Only a booking that has not been admitted or cancelled can be cancelled.")
        _lock_rooms(set(_booking_claims(reservation)))
        RoomClaim.objects.filter(reservation=reservation).update(blocking=False)
        reservation.status = Status.CANCELLED
        reservation.save(update_fields=["status"])
        _event(reservation, user, "reservation.cancel", "Reservation cancelled; rooms released.")
        return reservation


def check_in(pk, user):
    from apps.billing.services import open_folio

    with _write(user):
        reservation = _lock_reservation(pk)
        if reservation.status != Status.CONFIRMED:
            raise Conflict("Only a confirmed reservation can be checked in.")
        claims = _booking_claims(reservation)
        rooms = _lock_rooms(set(claims))
        now = timezone.now()
        today = selectors.business_date(now)
        if not reservation.arrival <= today < reservation.departure:
            raise Conflict("Today is outside this reservation's booked nights.")
        if any(not c.blocking or c.start != reservation.arrival or c.end != reservation.departure for c in claims.values()):
            raise Conflict("Every booked room must have a confirmed claim for the stay.")
        if any(not room.is_active or room.cleanliness != Cleanliness.INSPECTED for room in rooms.values()):
            raise Conflict("Every booked room must be active and inspected before check-in.")
        if selectors.occupied_claims().filter(room_id__in=rooms).exists():
            raise Conflict("A booked room still has an occupant.")
        if RoomClaim.objects.filter(room_id__in=rooms, blocking=True, start__lte=today, end__gt=today).exclude(reservation=reservation).exists():
            raise Conflict("A booked room is blocked for today.")

        reservation.status = Status.CHECKED_IN
        reservation.checked_in_at = now
        reservation.save(update_fields=["status", "checked_in_at"])
        # The reservation lock protects first creation of its as-yet absent folio.
        open_folio(reservation, user)
        _event(reservation, user, "reservation.check_in", "Checked in; stay folio opened.")
        return reservation


def check_out(pk, user):
    from apps.billing.services import close_folio
    from apps.housekeeping.services import turnover
    from apps.restaurant.services import assert_no_open_orders

    with _write(user):
        reservation = _lock_reservation(pk)
        if reservation.status != Status.CHECKED_IN:
            raise Conflict("Only a checked-in reservation can be checked out.")
        # The restaurant guard locks the existing folio before any order. Holding
        # the reservation also protects an empty order scan against new orders.
        assert_no_open_orders(reservation)
        close_folio(reservation, user)
        rooms = _lock_rooms(set(_booking_claims(reservation)))
        now = timezone.now()
        today = selectors.business_date(now)
        reservation.status = Status.CHECKED_OUT
        reservation.checked_out_at = now
        reservation.save(update_fields=["status", "checked_out_at"])
        claims = RoomClaim.objects.filter(reservation=reservation)
        # Retain the sold prefix. For zero elapsed nights retain the original,
        # nonempty interval as history but release the entire claim.
        claims.filter(start__gte=today).update(blocking=False)
        claims.filter(start__lt=today, end__gt=today).update(end=today)
        for room in rooms.values():
            turnover(room, user)
        _event(reservation, user, "reservation.check_out", "Checked out; folio closed and turnover requested.")
        return reservation
