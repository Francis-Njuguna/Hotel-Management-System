"""One staff-to-staff journey; no service calls or ORM writes during business actions."""

from decimal import Decimal

import pytest

from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.core.models import AuditEvent
from apps.housekeeping.models import CleaningTask
from apps.lodging.models import Reservation, ReservationEvent, Room, RoomClaim

from .support import action, as_user, booking, create, expect, food, get, money, page, patch, request


pytestmark = pytest.mark.django_db


def dashboard_matches_postings(manager, today, billed, collected):
    # Independent ledger arithmetic; importantly, do not join lines with tenders or add orders twice.
    lines = InvoiceItem.objects.filter(created_at__date=today).values_list("quantity", "unit_price")
    receipts = Payment.objects.filter(created_at__date=today).values_list("amount", flat=True)
    actual_billed = sum((qty * rate for qty, rate in lines), Decimal("0.00"))
    actual_collected = sum(receipts, Decimal("0.00"))
    assert (actual_billed, actual_collected) == (Decimal(billed), Decimal(collected))
    dashboard = get(manager, "dashboard")
    assert dashboard["date"] == today.isoformat()
    assert (dashboard["metrics"]["billed"], dashboard["metrics"]["collected"]) == (billed, collected)
    return dashboard


def assert_not_checked_out(rid, invoice_id, room_ids):
    saved = Reservation.objects.get(pk=rid)
    assert saved.status == "checked_in" and saved.checked_out_at is None
    assert Invoice.objects.get(pk=invoice_id).closed_at is None
    assert not CleaningTask.objects.filter(room_id__in=room_ids).exists()


def test_stay_room_service_settlement_checkout_and_inspected_turnover(employee, today):
    manager = as_user(employee("Hotel Manager"))
    receptionist = employee("Receptionist")
    desk = as_user(receptionist)
    kitchen = as_user(employee("Restaurant Staff"))
    office = as_user(employee("Accountant"))
    cleaner = employee("Housekeeping Staff")
    cleaning = as_user(cleaner)

    rooms = [create(manager, "rooms", {"number": number, "category": "Double", "nightly_rate": rate,
                                      "capacity": 2, "facilities": ["desk"], "description": "Synthetic room"})
             for number, rate in (("QA-201", "1250.00"), ("QA-202", "750.00"))]
    person = create(desk, "guests", {"full_name": "QA Journey Guest", "email": "journey@example.invalid"})
    room_ids = [r["id"] for r in rooms]
    room_id, sibling = room_ids
    booking_data = booking(person["id"], room_ids, today)
    available = page(desk, "rooms/availability", {key: booking_data[key] for key in ("arrival", "departure")})
    assert {r["id"] for r in available["results"]} == set(room_ids)
    reservation = create(desk, "reservations", booking_data)
    rid = reservation["id"]
    assert reservation["status"] == "confirmed" and reservation["guest_name"] == person["full_name"]
    schedule = get(manager, "dashboard")["metrics"]
    assert (schedule["check_ins"], schedule["reserved_rooms"], schedule["occupied_rooms"]) == (1, 2, 0)
    expect(request(desk, "patch", f"rooms/{room_id}", {"nightly_rate": "2500.00"}), 403)
    for key in room_ids:
        patch(manager, f"rooms/{key}", {"nightly_rate": "2500.00"})  # neither agreed rate may change
    assert action(desk, f"reservations/{rid}/check_in")["status"] == "checked_in"
    assert {r["id"] for r in page(desk, "rooms")["results"] if r["occupied"]} == set(room_ids)
    invoices = page(office, "invoices")["results"]
    assert len(invoices) == 1 and invoices[0]["reservation"] == rid
    invoice_id = invoices[0]["id"]
    inv = f"invoices/{invoice_id}"
    money(get(desk, inv), "4000.00", "0.00", "4000.00")
    assert set(InvoiceItem.objects.filter(invoice_id=invoice_id).values_list("quantity", "unit_price")) == {
        (2, Decimal("1250.00")), (2, Decimal("750.00")),
    }

    meal = food(kitchen)
    payload = {"reservation": rid, "room": room_id, "items": [{"menu_item": meal["id"], "quantity": 1}]}
    order = create(kitchen, "orders", payload)
    assert order["status"] == "pending" and order["total"] == "850.25"
    path = f"orders/{order['id']}/transition"
    patch(kitchen, f"menu-items/{meal['id']}", {"price": "925.00"})
    for status in ("confirmed", "preparing", "ready"):
        assert action(kitchen, path, {"status": status})["status"] == status
        money(get(office, inv), "4000.00", "0.00", "4000.00")
    assert action(kitchen, path, {"status": "served"})["status"] == "served"
    charged = get(office, inv)
    money(charged, "4850.25", "0.00", "4850.25")
    line_ids = {line["id"] for line in charged["items"]}
    assert action(kitchen, path, {"status": "served"})["status"] == "served"
    assert {line["id"] for line in get(office, inv)["items"]} == line_ids
    assert Invoice.objects.count() == 1 and not Payment.objects.exists()

    # These are two synthetic received-tender fixtures, not a gateway/payment simulation.
    first = {"amount": "2000.00", "method": "cash", "reference": "QA-JOURNEY-RECEIVED-1"}
    receipt1 = action(office, f"{inv}/payments", first)
    assert action(office, f"{inv}/payments", first)["receipt_number"] == receipt1["receipt_number"]
    money(get(office, inv), "4850.25", "2000.00", "2850.25")
    dashboard_matches_postings(manager, today, "4850.25", "2000.00")
    expect(request(desk, "post", f"reservations/{rid}/check_out", {}), 409)  # only blocker: balance
    assert_not_checked_out(rid, invoice_id, room_ids)

    receipt2 = action(office, f"{inv}/payments", {
        "amount": "2850.25", "method": "bank", "reference": "QA-JOURNEY-RECEIVED-2",
    })
    assert receipt2["receipt_number"] != receipt1["receipt_number"]
    money(get(office, inv), "4850.25", "4850.25", "0.00")
    pending = create(kitchen, "orders", payload)
    expect(request(desk, "post", f"reservations/{rid}/check_out", {}), 409)  # only blocker: open order
    assert_not_checked_out(rid, invoice_id, room_ids)
    assert action(kitchen, f"orders/{pending['id']}/transition", {"status": "cancelled"})["status"] == "cancelled"

    checkout = f"reservations/{rid}/check_out"
    assert action(desk, checkout)["status"] == "checked_out"
    assert Invoice.objects.get(pk=invoice_id).closed_at is not None
    saved = Reservation.objects.get(pk=rid)
    assert saved.checked_in_at <= saved.checked_out_at and saved.departure.isoformat() == reservation["departure"]
    assert not RoomClaim.objects.filter(reservation=saved, blocking=True).exists()  # same-day early release
    tasks = list(CleaningTask.objects.order_by("room_id"))
    assert len(tasks) == 2 and {t.room_id for t in tasks} == set(room_ids)
    assert all(t.status == "pending" and t.assignee_id is None for t in tasks)
    task = next(t for t in tasks if t.room_id == room_id)
    assert set(Room.objects.filter(cleanliness="dirty").values_list("id", flat=True)) == set(room_ids)
    assert not any(r["occupied"] for r in page(desk, "rooms")["results"])
    checked_out_at = saved.checked_out_at
    repeated = expect(request(desk, "post", checkout, {}), 200, 409)
    if repeated.status_code == 200:  # a no-op replay is also safe; it is never a second checkout
        assert repeated.json()["status"] == "checked_out" and repeated.json()["id"] == rid
    saved.refresh_from_db()
    assert saved.checked_out_at == checked_out_at
    assert ReservationEvent.objects.filter(reservation=saved, status="checked_out").count() == 1
    assert CleaningTask.objects.count() == 2 and Payment.objects.count() == 2
    dash = dashboard_matches_postings(manager, today, "4850.25", "4850.25")
    assert dash["metrics"]["occupied_rooms"] == 0 and dash["metrics"]["cleaning_rooms"] == 2
    assert {t.pk for t in tasks} == {t["id"] for t in dash["tasks"]}
    money(get(office, inv), "4850.25", "4850.25", "0.00")  # no prorating or refund on early departure
    history = get(manager, f"guests/{person['id']}/history")
    assert {r["id"] for r in history["reservations"]} == {rid}
    assert {p["id"] for p in history["payments"]} == {receipt1["id"], receipt2["id"]}
    assert set(ReservationEvent.objects.filter(reservation_id=rid, actor=receptionist).values_list("status", flat=True)) >= {
        "confirmed", "checked_in", "checked_out",
    }
    assert not AuditEvent.objects.filter(summary__icontains=first["reference"]).exists()

    next_person = create(desk, "guests", {"full_name": "QA Next Guest", "email": "next@example.invalid"})
    next_id = create(desk, "reservations", booking(next_person["id"], [room_id], today))["id"]
    transition = f"cleaning-tasks/{task.pk}/transition"
    assert action(manager, transition, {"status": "assigned", "assignee": cleaner.pk})["status"] == "assigned"
    for status in ("in_progress", "completed"):
        assert action(cleaning, transition, {"status": status})["status"] == status
    assert Room.objects.get(pk=room_id).cleanliness == "dirty"
    expect(request(cleaning, "post", transition, {"status": "inspected"}), 403)
    expect(request(desk, "post", f"reservations/{next_id}/check_in", {}), 409)
    assert not Invoice.objects.filter(reservation_id=next_id).exists()
    assert action(manager, transition, {"status": "inspected"})["status"] == "inspected"
    assert Room.objects.get(pk=room_id).cleanliness == "inspected"
    assert Room.objects.get(pk=sibling).cleanliness == "dirty"  # inspection releases only its own room
    assert action(desk, f"reservations/{next_id}/check_in")["status"] == "checked_in"
    assert not get(manager, f"guests/{next_person['id']}/history")["payments"]  # no prior occupant's tender
