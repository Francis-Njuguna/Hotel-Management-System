"""The dated sale of a room, its actual occupant, and its readiness are distinct facts."""

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Lower, Trim
from django.db.models.lookups import Exact


ZERO = Decimal("0.00")
MAX_RATE = Decimal("9999999999.99")
ROOM_EXCLUSION = "lodging_roomclaim_no_overlap"


def new_guest_reference():
    return f"G-{uuid4().hex.upper()}"


def validate_facilities(value):
    if not isinstance(value, list) or len(value) > 64:
        raise ValidationError("Provide a list of up to 64 room facilities.")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 120 for item in value):
        raise ValidationError("Each facility must be nonblank text of at most 120 characters.")
    if any("\x00" in item or any(0xD800 <= ord(char) <= 0xDFFF for char in item) for item in value):
        raise ValidationError("Facility names must contain valid text.")


def finite_interval(start, end):
    # PostgreSQL date also supports +/-infinity; these aren't hotel calendar dates.
    def finite(column):
        return models.Func(F(column), function="ISFINITE", output_field=models.BooleanField())

    return Q(finite(start), finite(end), **{f"{start}__lt": F(end)})


def claim_window():
    return models.Func(
        F("start"), F("end"), Value("[)"), function="DATERANGE", output_field=DateRangeField()
    )


class Guest(models.Model):
    full_name = models.CharField(max_length=160)
    email = models.EmailField(max_length=254, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    reference = models.CharField(max_length=64, unique=True, default=new_guest_reference)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(full_name__regex=r"\S"), name="lodging_guest_name_present"),
            models.CheckConstraint(condition=Q(reference__regex=r"\S"), name="lodging_guest_ref_present"),
            models.CheckConstraint(
                condition=Q(email=Lower(Trim("email"))) & ~Q(email__regex=r"\s"),
                name="lodging_guest_canonical_email",
            ),
            models.UniqueConstraint(Lower("email"), condition=~Q(email=""), name="lodging_guest_email_ci_uniq"),
        ]

    def save(self, *args, **kwargs):
        self.full_name = self.full_name.strip()
        self.reference = self.reference.strip() or new_guest_reference()
        self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.reference


class RoomCategory(models.TextChoices):
    SINGLE = "Single", "Single"
    DOUBLE = "Double", "Double"
    TWIN = "Twin", "Twin"
    DELUXE = "Deluxe", "Deluxe"
    SUITE = "Suite", "Suite"
    FAMILY = "Family", "Family"


class Cleanliness(models.TextChoices):
    INSPECTED = "inspected", "Inspected"
    DIRTY = "dirty", "Dirty"


class Room(models.Model):
    Category = RoomCategory
    Cleanliness = Cleanliness

    number = models.CharField(max_length=24, unique=True)
    category = models.CharField(max_length=16, choices=RoomCategory.choices)
    nightly_rate = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    capacity = models.IntegerField(validators=[MinValueValidator(1)])
    description = models.TextField(blank=True, default="")
    facilities = models.JSONField(default=list, blank=True, validators=[validate_facilities])
    image = models.ImageField(upload_to="rooms/", max_length=255, blank=True)
    cleanliness = models.CharField(max_length=16, choices=Cleanliness.choices, default=Cleanliness.INSPECTED)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(number__regex=r"\S"), name="lodging_room_number_present"),
            models.CheckConstraint(condition=Q(capacity__gt=0), name="lodging_room_capacity_positive"),
            models.CheckConstraint(
                condition=Q(nightly_rate__range=(ZERO, MAX_RATE)), name="lodging_room_rate_valid"
            ),
            models.CheckConstraint(condition=Q(category__in=RoomCategory.values), name="lodging_room_category_valid"),
            models.CheckConstraint(condition=Q(cleanliness__in=Cleanliness.values), name="lodging_room_clean_valid"),
            models.CheckConstraint(
                condition=Exact(models.Func(F("facilities"), function="JSONB_TYPEOF", output_field=models.CharField()), Value("array")),
                name="lodging_room_facilities_array",
            ),
        ]

    def __str__(self):
        return self.number


class ReservationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    CHECKED_IN = "checked_in", "Checked in"
    CHECKED_OUT = "checked_out", "Checked out"
    CANCELLED = "cancelled", "Cancelled"


class Reservation(models.Model):
    Status = ReservationStatus

    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name="reservations")
    arrival = models.DateField()
    departure = models.DateField()
    status = models.CharField(max_length=16, choices=ReservationStatus.choices, default=ReservationStatus.PENDING)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=finite_interval("arrival", "departure"), name="lodging_res_dates_valid"),
            models.CheckConstraint(
                condition=(
                    Q(status__in=["pending", "confirmed", "cancelled"], checked_in_at__isnull=True, checked_out_at__isnull=True)
                    | Q(status="checked_in", checked_in_at__isnull=False, checked_out_at__isnull=True)
                    | Q(status="checked_out", checked_in_at__isnull=False, checked_out_at__isnull=False, checked_out_at__gte=F("checked_in_at"))
                ),
                name="lodging_res_actual_times",
            ),
        ]
        indexes = [
            models.Index(fields=["guest", "created_at"], name="lodging_res_guest_time"),
            models.Index(fields=["status", "arrival"], name="lodging_res_arrivals"),
            models.Index(fields=["status", "departure"], name="lodging_res_departures"),
        ]


class RoomClaim(models.Model):
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="claims")
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="claims", null=True, blank=True)
    maintenance = models.ForeignKey(
        "housekeeping.MaintenanceRequest", on_delete=models.PROTECT, related_name="claims", null=True, blank=True
    )
    start = models.DateField()
    end = models.DateField()
    blocking = models.BooleanField(default=False)
    nightly_rate = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)])

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(reservation__isnull=False, maintenance__isnull=True) | Q(reservation__isnull=True, maintenance__isnull=False)),
                name="lodging_claim_one_source",
            ),
            models.CheckConstraint(condition=finite_interval("start", "end"), name="lodging_claim_dates_valid"),
            models.CheckConstraint(
                condition=Q(nightly_rate__range=(ZERO, MAX_RATE)) & (Q(maintenance__isnull=True) | Q(nightly_rate=ZERO)),
                name="lodging_claim_rate_valid",
            ),
            models.UniqueConstraint(fields=["reservation", "room"], name="lodging_claim_booking_room_uniq"),
            ExclusionConstraint(
                name=ROOM_EXCLUSION,
                expressions=[("room", RangeOperators.EQUAL), (claim_window(), RangeOperators.OVERLAPS)],
                condition=Q(blocking=True),
            ),
        ]


class ReservationEvent(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lodging_events")
    status = models.CharField(max_length=16, choices=ReservationStatus.choices)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["reservation", "created_at", "id"], name="lodging_event_timeline")]
        constraints = [models.CheckConstraint(condition=Q(status__in=ReservationStatus.values), name="lodging_event_status_valid")]
