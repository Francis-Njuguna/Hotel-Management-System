"""Order commands. Binding, accepted prices and quantities do not change after sale."""

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.billing.models import Invoice
from apps.core.access import can, is_manager
from apps.core.api import Conflict
from apps.core.events import record
from apps.lodging.models import Reservation, Room, RoomClaim

from .models import MenuItem, Order, OrderItem, OrderStatus


RESTAURANT_STAFF = "Restaurant Staff"
ELIGIBLE_FOR_ASSIGNMENT = (OrderStatus.PENDING, OrderStatus.CONFIRMED)
FINAL_STATES = (OrderStatus.SERVED, OrderStatus.CANCELLED)
NEXT_STATE = {
    OrderStatus.PENDING: OrderStatus.CONFIRMED,
    OrderStatus.CONFIRMED: OrderStatus.PREPARING,
    OrderStatus.PREPARING: OrderStatus.READY,
    OrderStatus.READY: OrderStatus.SERVED,
}
UNCHANGED = object()


def has_order_scope(user):
    # There is one restaurant department at this property, not a personal queue.
    return is_manager(user) or user.groups.filter(name=RESTAURANT_STAFF).exists()


def _require_order_work(user):
    if not can(user, "restaurant.work") or not has_order_scope(user):
        raise PermissionDenied()


def _assignee(assignee_id):
    if assignee_id is None:
        return None
    # Staff administration takes the User lock before changing active status or
    # group membership. Query the group AFTER this lock, not in a pre-lock join.
    candidate = get_user_model().objects.select_for_update(no_key=True).filter(pk=assignee_id).first()
    if (candidate is None or not candidate.is_active
            or not candidate.groups.filter(name=RESTAURANT_STAFF).exists()
            or not can(candidate, "restaurant.work")):
        raise ValidationError({"assignee": "Choose an active restaurant staff member."})
    return candidate


def _lock_stay(reservation_id):
    """Lock existing parents in order, including the creation lock for an absent folio."""
    stay = Reservation.objects.select_for_update().filter(pk=reservation_id).first()
    if stay is None:
        raise Conflict("Room service needs a checked-in stay with an open folio.")
    invoice = Invoice.objects.select_for_update().filter(reservation_id=stay.pk).first()
    return stay, invoice


def _require_open_stay(stay, invoice):
    if stay.status != Reservation.Status.CHECKED_IN or invoice is None or invoice.closed_at is not None:
        raise Conflict("Room service needs a checked-in stay with an open folio.")


def _service_room(stay, room_id, *, check_active=True):
    # After admission the named rooms cannot be amended. The locked stay owns
    # its claims. Do not infer this booking or its guest from a room number/date.
    claims = RoomClaim.objects.filter(reservation_id=stay.pk)
    if room_id is None:
        candidates = list(claims.order_by("room_id").values_list("room_id", flat=True)[:2])
        if len(candidates) != 1:
            raise ValidationError({"room": "Choose a room belonging to the selected stay."})
        room_id = candidates[0]
    elif not claims.filter(room_id=room_id).exists():
        raise ValidationError({"room": "Choose a room belonging to the selected stay."})
    if check_active and not Room.objects.select_for_update(no_key=True).filter(pk=room_id, is_active=True).exists():
        raise Conflict("The selected service room is not active.")
    return room_id


@transaction.atomic
def create_order(*, user, items, reservation=None, room=None, assignee=None):
    _require_order_work(user)
    if reservation is not None:
        stay, invoice = _lock_stay(reservation)
        _require_open_stay(stay, invoice)
        room = _service_room(stay, room)
    elif room is not None:
        raise ValidationError({"room": "Select a checked-in stay for room service."})

    staff = _assignee(assignee)
    item_ids = {line["menu_item"] for line in items}
    if not items or len(item_ids) != len(items):
        raise ValidationError({"items": "Choose one or more distinct menu items."})
    if any(type(line["quantity"]) is not int or not 1 <= line["quantity"] <= 2**31 - 1 for line in items):
        raise ValidationError({"items": "Each quantity must be a positive whole number."})

    # Sort before locking every requested catalog row. A menu edit that wins
    # this race determines the entire sale; no header or partial ticket yet.
    menu = {item.pk: item for item in MenuItem.objects.select_for_update(no_key=True)
            .filter(pk__in=item_ids).only("id", "available", "price").order_by("pk")}
    if len(menu) != len(item_ids) or not all(item.available for item in menu.values()):
        raise Conflict("One or more selected menu items are no longer available.")

    order = Order.objects.create(reservation_id=reservation, room_id=room, assignee=staff)
    OrderItem.objects.bulk_create([
        OrderItem(order=order, menu_item_id=line["menu_item"], quantity=line["quantity"],
                  unit_price=menu[line["menu_item"]].price)
        for line in items
    ])
    record(user, "order.created", order, "Restaurant order placed")
    return order


@transaction.atomic
def assert_no_open_orders(reservation):
    """Checkout must call inside its transaction, before locking rooms or doing turnover.

    Even an empty order scan is protected by the same reservation lock as
    create_order. A standalone invocation is a check, not a hold after return.
    """
    stay, _invoice = _lock_stay(reservation.pk)
    blocker = (Order.objects.select_for_update().filter(reservation_id=stay.pk)
               .exclude(status__in=FINAL_STATES).order_by("pk").values_list("pk", flat=True).first())
    if blocker is not None:
        raise Conflict("Serve or cancel open room-service orders before checkout.")


def _mark_served(order, user):
    """The caller owns the locked order and the surrounding posting transaction."""
    if order.status == OrderStatus.SERVED:
        return  # The billing service checks the complete original posting on replay.
    if order.status != OrderStatus.READY:
        raise Conflict("Only a ready order can be served.")
    order.status = OrderStatus.SERVED
    order.save(update_fields=["status"])
    record(user, "order.served", order, "Restaurant order served")


def lock_dine_in_for_post(order_pk, binding, user):
    """Billing calls this *after* inserting its private candidate invoice.

    Updating status is itself an order lock. For dine-in, waiting until here
    lets the financial owner create/roll back its candidate before that lock,
    while keeping the lifecycle rule and its event in the restaurant app.
    """
    _require_order_work(user)
    order = Order.objects.select_for_update().get(pk=order_pk)
    if binding != (None, None) or (order.reservation_id, order.room_id) != binding:
        raise Conflict("The dine-in order destination is not valid.")
    _mark_served(order, user)
    return order


@transaction.atomic
def change_order(order, user, *, status=None, assignee=UNCHANGED):
    from apps.billing.services import post_order

    _require_order_work(user)
    if status is None and assignee is UNCHANGED:
        raise ValidationError("Specify a target status or an assignee.")
    if status == OrderStatus.SERVED and assignee is not UNCHANGED:
        raise Conflict("Staff assignment is only available on pending or confirmed orders.")

    if status == OrderStatus.SERVED and order.reservation_id is None:
        # The ordering for a new standalone invoice is candidate → order. In
        # particular, do NOT mark the order served before entering post_order.
        post_order(order, user)
        order.refresh_from_db(fields=["status"])
        if order.status != OrderStatus.SERVED:
            raise Conflict("The dine-in order was not served.")
        return order

    stay = invoice = None
    if order.reservation_id is not None:
        stay, invoice = _lock_stay(order.reservation_id)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if (locked.reservation_id, locked.room_id) != (order.reservation_id, order.room_id):
        raise Conflict("The order destination changed. Reload the order.")

    if status == OrderStatus.SERVED and locked.status == OrderStatus.SERVED:
        # Even after checkout this can read the existing posting, never post a
        # late charge to this or any subsequent occupant's folio.
        post_order(locked, user)
        return locked
    if stay is not None:
        _require_open_stay(stay, invoice)
        _service_room(stay, locked.room_id, check_active=status != OrderStatus.CANCELLED)

    if status == OrderStatus.SERVED:
        _mark_served(locked, user)
        post_order(locked, user)
        return locked

    if assignee is not UNCHANGED and locked.status not in ELIGIBLE_FOR_ASSIGNMENT:
        raise Conflict("Staff assignment is only available on pending or confirmed orders.")
    assigning_only = assignee is not UNCHANGED and status in (None, locked.status)
    if not assigning_only:
        cancelling = status == OrderStatus.CANCELLED and locked.status not in FINAL_STATES
        if not cancelling and status != NEXT_STATE.get(locked.status):
            raise Conflict("This transition is not available from the current order status.")

    changes = []
    if assignee is not UNCHANGED:
        selected = _assignee(assignee)
        if locked.assignee_id != assignee:
            locked.assignee = selected
            changes.append("assignee")
    if status is not None and status != locked.status:
        locked.status = status
        changes.append("status")
    if changes:
        locked.save(update_fields=changes)
        if "status" in changes:
            record(user, "order.transition", locked, f"Restaurant order moved to {locked.status}")
        else:
            record(user, "order.assignment", locked, "Restaurant order assignment updated")
    return locked
