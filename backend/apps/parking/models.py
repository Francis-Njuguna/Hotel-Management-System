from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Upper


# Explicit str.split() whitespace characters: a database locale's [:space:]
# need not include, for example, a non-breaking space pasted into a plate.
_SPACING = (
    " \t\n\v\f\r\x1c\x1d\x1e\x1f\x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)
_REMOVE_SPACING = str.maketrans("", "", _SPACING)


def normalize_plate(value: str) -> str:
    """Keep significant characters (including hyphens and leading zeroes)."""
    return value.translate(_REMOVE_SPACING).upper()


class ParkingSpace(models.Model):
    code = models.CharField(max_length=24)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["code"], name="parking_space_code_unique"),
            models.CheckConstraint(condition=Q(code__regex=f"[^{_SPACING}]"), name="parking_space_code_nonblank"),
        ]


class Vehicle(models.Model):
    guest = models.ForeignKey("lodging.Guest", on_delete=models.PROTECT, related_name="vehicles")
    plate = models.CharField(max_length=32)

    class Meta:
        ordering = ["plate", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["plate"], name="parking_vehicle_plate_unique"),
            models.CheckConstraint(
                condition=~Q(plate="") & ~Q(plate__regex=f"[{_SPACING}]") & Q(plate=Upper("plate")),
                name="parking_vehicle_plate_canonical",
            ),
        ]

    def save(self, *args, **kwargs):
        if isinstance(self.plate, str):
            self.plate = normalize_plate(self.plate)
        return super().save(*args, **kwargs)


class Allocation(models.Model):
    space = models.ForeignKey(ParkingSpace, on_delete=models.PROTECT, related_name="allocations")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="allocations")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-started_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["space"], condition=Q(ended_at__isnull=True), name="parking_one_active_per_space"
            ),
            models.UniqueConstraint(
                fields=["vehicle"], condition=Q(ended_at__isnull=True), name="parking_one_active_per_vehicle"
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("started_at")),
                name="parking_allocation_time_order",
            ),
        ]
