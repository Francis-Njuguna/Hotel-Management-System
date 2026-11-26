"""Synthetic fixtures only; no real guest identities or tender records."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.lodging.models import Guest, Reservation, Room, RoomClaim
from apps.restaurant.models import MenuItem, Order, OrderItem


def staff(role):
    user = get_user_model().objects.create_user(username=f"ledger-test-{uuid4().hex}")
    user.groups.add(Group.objects.get(name=role))  # Use actual provisioned grants.
    return user


def admitted(*rates, nights=2):
    start = timezone.localdate()
    reservation = Reservation.objects.create(
        guest=Guest.objects.create(full_name="Synthetic billing guest", reference=f"TEST-{uuid4().hex}"),
        arrival=start, departure=start + timedelta(days=nights), status="checked_in", checked_in_at=timezone.now(),
    )
    for rate in rates:
        room = Room.objects.create(number=f"TEST-{uuid4().hex[:12]}", category="Single", capacity=1,
                                   nightly_rate=Decimal("999.99"))
        RoomClaim.objects.create(reservation=reservation, room=room, start=start, end=reservation.departure,
                                 nightly_rate=Decimal(rate), blocking=True)
    return reservation


def meal(lines, *, reservation=None, room=None, status="served"):
    order = Order.objects.create(reservation=reservation, room=room, status=status)
    for name, quantity, agreed in lines:
        menu = MenuItem.objects.create(name=name, category="Test", price=Decimal("97.15"), available=True)
        OrderItem.objects.create(order=order, menu_item=menu, quantity=quantity, unit_price=Decimal(agreed))
    return order


def tender(reference, amount="1.00", method="cash"):
    return {"amount": amount, "method": method, "reference": f"TEST-{reference}"}
