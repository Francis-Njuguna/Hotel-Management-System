"""Transactional ledger commands. No command takes money or contacts a provider.

Automatic postings belong to an already-authorized lodging/restaurant transition
and commit (or roll back) with it. Manual postings have a separate finance gate.
Lock existing owners in this order: reservation → invoice → order. An absent folio is
protected by its reservation. Never use client-supplied totals or a pre-lock balance.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.api import Conflict
from apps.core.events import record
from apps.lodging.models import Reservation, RoomClaim
from apps.restaurant.models import Order, OrderItem

from .access import require_finance
from .models import ZERO, Invoice, InvoiceItem, Payment
from .serializers import ChargeCommand, PaymentCommand


def _lock_reservation(pk):
    return Reservation.objects.select_for_update().get(pk=pk)


def _folio(reservation):
    return Invoice.objects.select_for_update().filter(reservation=reservation).first()


def _require_open(invoice):
    if invoice.closed_at is not None:
        raise Conflict("This invoice is closed to new entries.")


@transaction.atomic
def open_folio(reservation, user):
    """Post the contracted nights once per named room at admission."""
    reservation = _lock_reservation(reservation.pk)
    if reservation.status != "checked_in":
        raise Conflict("A folio can only be opened for a checked-in reservation.")
    existing = _folio(reservation)
    if existing is not None:
        _require_open(existing)
        return existing

    nights = (reservation.departure - reservation.arrival).days
    claims = list(RoomClaim.objects.filter(reservation=reservation).select_related("room").order_by("pk"))
    if nights <= 0 or not claims:
        raise Conflict("A folio requires booked rooms and a nonempty stay interval.")

    invoice = Invoice.objects.create(reservation=reservation)
    InvoiceItem.objects.bulk_create([
        InvoiceItem(invoice=invoice, source_key=f"room:{claim.pk}", description=f"Room {claim.room.number} — accommodation",
                    quantity=nights, unit_price=claim.nightly_rate)
        for claim in claims
    ])
    record(user, "billing.folio.open", invoice, "Opened reservation folio and posted agreed room nights.")
    return invoice


@transaction.atomic
def close_folio(reservation, user):
    """Only a settled folio with no unserved obligations can close. Never reprice nights."""
    from apps.restaurant.services import assert_no_open_orders

    reservation = _lock_reservation(reservation.pk)
    invoice = _folio(reservation)
    if invoice is None:
        raise Conflict("No folio exists for this reservation.")
    if invoice.closed_at is not None:
        return invoice
    if reservation.status != "checked_in":
        raise Conflict("Only a checked-in reservation's folio can be closed.")
    assert_no_open_orders(reservation)
    if invoice.balance != ZERO:
        raise Conflict("Settle the outstanding folio balance before checkout.")
    invoice.closed_at = timezone.now()
    invoice.save(update_fields=["closed_at"])
    record(user, "billing.folio.close", invoice, "Closed settled reservation folio.")
    return invoice


def _served_order(pk, binding):
    order = Order.objects.select_for_update().get(pk=pk)
    if (order.reservation_id, order.room_id) != binding:
        raise Conflict("The order binding changed while posting.")
    if order.status != "served":
        raise Conflict("Only served orders may be billed.")
    return order


def _order_lines(order):
    prefix = f"order:{order.pk}:line:"
    items = OrderItem.objects.filter(order=order).select_related("menu_item").order_by("pk")
    lines = {f"{prefix}{item.pk}": item for item in items}
    if not lines:
        raise Conflict("An order without items cannot be billed.")
    # A committed retry finds the original *complete* posting. Never patch up
    # partial data, move lines, or compare snapshots to mutable catalog prices/names.
    previous = list(InvoiceItem.objects.filter(source_key__startswith=prefix)
                    .values_list("source_key", "invoice_id", "quantity", "unit_price"))
    if not previous:
        return lines, None
    owners = {owner for _, owner, _, _ in previous}
    if (len(owners) != 1 or len(previous) != len(lines) or
            any(key not in lines or (qty, price) != (lines[key].quantity, lines[key].unit_price)
                for key, _, qty, price in previous)):
        raise Conflict("The served order conflicts with its original posting.")
    return lines, owners.pop()


def _post_lines(invoice, lines, user, order):
    InvoiceItem.objects.bulk_create([
        InvoiceItem(invoice=invoice, source_key=key, description=item.menu_item.name,
                    quantity=item.quantity, unit_price=item.unit_price)
        for key, item in lines.items()
    ])
    record(user, "billing.order.post", invoice, f"Posted items for served order #{order.pk}.")
    return invoice


class _ExistingPosting(Exception):
    """Roll back our speculative standalone invoice, not the winner's posting."""


def _post_standalone(order_pk, binding, user):
    from apps.restaurant.services import lock_dine_in_for_post

    try:
        with transaction.atomic():
            # Private candidate BEFORE the order lock. A losing retry must leave
            # neither an empty invoice nor an event. A missing line isn't a lock.
            candidate = Invoice.objects.create()
            # Restaurant owns READY → SERVED and its audit. This hook locks and
            # revalidates the destination and state, inside the candidate's savepoint.
            order = lock_dine_in_for_post(order_pk, binding, user)
            lines, previous = _order_lines(order)
            if previous is not None:
                raise _ExistingPosting(previous)
            return _post_lines(candidate, lines, user, order)
    except _ExistingPosting as replay:
        # Read only: never lock the winner's invoice while holding an order.
        original = Invoice.objects.filter(pk=replay.args[0], reservation__isnull=True).first()
        if original is None:
            raise Conflict("The dine-in posting conflicts with its invoice binding.") from None
        return original


@transaction.atomic
def post_order(order, user):
    """Called inside serve: copy accepted quantities/prices, never collect payment."""
    # Discover ownership without a lock, then verify under the ordered locks.
    binding = Order.objects.values_list("reservation_id", "room_id").get(pk=order.pk)
    if binding != (order.reservation_id, order.room_id):
        raise Conflict("The order destination changed. Reload the order before posting.")
    reservation_id, _ = binding
    if reservation_id is None:
        return _post_standalone(order.pk, binding, user)

    reservation = _lock_reservation(reservation_id)
    invoice = _folio(reservation)
    if invoice is None:
        raise Conflict("Room service requires the reservation's folio.")
    order = _served_order(order.pk, binding)
    lines, previous = _order_lines(order)
    if previous is not None:
        if previous != invoice.pk:
            raise Conflict("The room-service posting conflicts with its original folio.")
        return invoice

    _require_open(invoice)
    if reservation.status != "checked_in":
        raise Conflict("New room service requires a checked-in reservation.")
    claims = RoomClaim.objects.filter(reservation=reservation)
    if ((order.room_id is None and claims.count() != 1) or
            (order.room_id is not None and not claims.filter(room_id=order.room_id).exists())):
        raise Conflict("Room service must identify a booked room on this reservation.")
    return _post_lines(invoice, lines, user, order)


def _lock_invoice(invoice):
    owner = Invoice.objects.values_list("reservation_id", flat=True).get(pk=invoice.pk)
    if owner is not None:
        _lock_reservation(owner)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.reservation_id != owner:
        raise Conflict("Invoice ownership changed while posting.")
    return locked


@transaction.atomic
def post_charge(invoice, user, payload):
    require_finance(user)
    command = ChargeCommand(data=payload)
    command.is_valid(raise_exception=True)
    data = command.validated_data
    invoice = _lock_invoice(invoice)
    key = f"extra:{invoice.pk}:{data['reference']}"
    posting = {name: data[name] for name in ("description", "quantity", "unit_price")}
    existing = InvoiceItem.objects.filter(source_key=key).first()
    if existing is not None:
        if existing.invoice_id != invoice.pk or any(getattr(existing, k) != v for k, v in posting.items()):
            raise Conflict("Charge reference conflicts with the submitted entry.")
        return existing, False
    _require_open(invoice)
    item = InvoiceItem.objects.create(invoice=invoice, source_key=key, **posting)
    record(user, "billing.charge.post", item, "Posted an additional invoice charge.")
    return item, True


def _payment_replay(payment, invoice, data):
    if (payment.invoice_id, payment.amount, payment.method) != (invoice.pk, data["amount"], data["method"]):
        # Do not return another invoice, amount, receiver, reference or receipt.
        raise Conflict("Tender reference conflicts with the submitted entry.")
    return payment, False


@transaction.atomic
def record_payment(invoice, user, payload):
    """Record cash in hand or an externally verified tender, not a payment intent."""
    require_finance(user)
    command = PaymentCommand(data=payload)
    command.is_valid(raise_exception=True)
    data = command.validated_data
    invoice = _lock_invoice(invoice)
    existing = Payment.objects.filter(reference=data["reference"]).first()
    if existing is not None:
        return _payment_replay(existing, invoice, data)
    _require_open(invoice)
    if data["amount"] > invoice.balance:
        raise Conflict("The received amount exceeds the outstanding balance.")

    # Two different invoice locks do not serialize a property-wide tender key.
    # Let the unique index decide; exit the failed savepoint BEFORE re-reading.
    try:
        with transaction.atomic():
            payment = Payment.objects.create(invoice=invoice, received_by=user, **data)
    except IntegrityError as exc:
        cause = exc.__cause__
        if (getattr(cause, "sqlstate", None) != "23505" or
                getattr(getattr(cause, "diag", None), "table_name", None) != Payment._meta.db_table):
            raise
        existing = Payment.objects.filter(reference=data["reference"]).first()
        if existing is None:
            raise
        return _payment_replay(existing, invoice, data)
    record(user, "billing.payment.record", payment, "Recorded received tender and issued its receipt.")
    return payment, True
