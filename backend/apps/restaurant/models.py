from decimal import Decimal, localcontext

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


ZERO = Decimal("0.00")
MAX_PRICE = Decimal("9999999999.99")


class MenuItem(models.Model):
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    available = models.BooleanField(default=True)
    image = models.ImageField(upload_to="menu/", max_length=255, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="restaurant_menu_name_nonblank"),
            models.CheckConstraint(condition=Q(category__regex=r"\S"), name="restaurant_menu_cat_nonblank"),
            # The upper bound excludes PostgreSQL numeric NaN as well.
            models.CheckConstraint(condition=Q(price__range=(ZERO, MAX_PRICE)), name="restaurant_menu_price_range"),
        ]

    def __str__(self):
        return self.name


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready"
    SERVED = "served", "Served"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    Status = OrderStatus
    reservation = models.ForeignKey(
        "lodging.Reservation", on_delete=models.PROTECT, null=True, blank=True, db_index=False, related_name="orders"
    )
    room = models.ForeignKey(
        "lodging.Room", on_delete=models.PROTECT, null=True, blank=True, related_name="restaurant_orders"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="restaurant_orders"
    )
    status = models.CharField(max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["reservation", "status"], name="restaurant_ord_stay_status"),
            models.Index(fields=["status", "created_at"], name="restaurant_ord_status_time"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=OrderStatus.values), name="restaurant_order_valid_status"),
            models.CheckConstraint(
                condition=Q(room__isnull=True) | Q(reservation__isnull=False), name="restaurant_room_needs_stay"
            ),
        ]

    @property
    def guest_id(self):
        """No independent guest selection: the primary guest belongs to the stay."""
        return self.reservation.guest_id if self.reservation_id is not None else None

    @property
    def total(self):
        with localcontext() as ctx:
            ctx.prec = 42  # bigint number of lines × integer quantities × numeric(12,2)
            return sum((line.quantity * line.unit_price for line in self.items.all()), ZERO)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="restaurant_line_qty_positive"),
            models.CheckConstraint(condition=Q(unit_price__range=(ZERO, MAX_PRICE)), name="restaurant_line_price_range"),
        ]
