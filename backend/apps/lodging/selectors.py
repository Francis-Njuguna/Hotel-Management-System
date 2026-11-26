"""Read projections. An availability result is not a hold or permission to admit."""

from django.db.models import Exists, OuterRef, Prefetch
from django.utils import timezone

from .models import Reservation, ReservationEvent, ReservationStatus, Room, RoomClaim, claim_window


def business_date(instant=None):
    # Hotel nights are local to the property, not to a client/user's display zone.
    return timezone.localdate(instant, timezone.get_default_timezone())


def overlapping_claims(arrival, departure):
    # Use the same half-open range expression as the partial GiST exclusion/index.
    return RoomClaim.objects.filter(blocking=True).alias(nights=claim_window()).filter(nights__overlap=(arrival, departure))


def occupied_claims():
    # Even a guest overdue past the last booked night still physically occupies the room.
    return RoomClaim.objects.filter(reservation__status=ReservationStatus.CHECKED_IN)


def rooms(*, today=None):
    today = today if today is not None else business_date()
    maintenance_now = RoomClaim.objects.filter(
        room_id=OuterRef("pk"), maintenance__isnull=False, blocking=True, start__lte=today, end__gt=today
    )
    return Room.objects.annotate(
        occupied=Exists(occupied_claims().filter(room_id=OuterRef("pk"))),
        maintenance=Exists(maintenance_now),
    ).order_by("number", "pk")


def available_rooms(arrival, departure):
    conflicting = overlapping_claims(arrival, departure).filter(room_id=OuterRef("pk"))
    return rooms().filter(is_active=True).filter(~Exists(conflicting))


def reservations(*, with_events=False):
    claims = RoomClaim.objects.select_related("room").order_by("room__number", "room_id")
    result = Reservation.objects.select_related("guest").prefetch_related(Prefetch("claims", queryset=claims))
    if with_events:
        events = ReservationEvent.objects.select_related("actor").order_by("created_at", "pk")
        result = result.prefetch_related(Prefetch("events", queryset=events))
    return result.order_by("-created_at", "-pk")


def guest_visits(guest):
    return Reservation.objects.filter(guest=guest).order_by("-arrival", "-pk")


def guest_payments(guest, user):
    """None means not authorized, not a zero balance or an empty payment history."""
    from apps.core.access import can

    if not (can(user, "guests.view") and can(user, "billing.view")):
        return None

    from apps.billing.models import Payment

    # A lookup for this one guest's folios: no standalone/dine-in receipts, other
    # guests' funds, tender references or receiver details. Do not use the payment feed.
    return Payment.objects.filter(invoice__reservation__guest=guest).only("id", "invoice_id", "amount", "created_at").order_by("-created_at", "-pk")
