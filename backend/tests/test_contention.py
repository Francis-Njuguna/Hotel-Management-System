"""PostgreSQL transaction evidence, including controlled reversal and forced rollback."""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.billing.models import Invoice, Payment
from apps.core.models import AuditEvent
from apps.housekeeping.models import CleaningTask
from apps.lodging.models import Reservation, ReservationEvent, RoomClaim
from apps.parking.models import Allocation
from apps.restaurant.models import Order

from .overlap import overlap
from .support import action, booking, create, expect, food, get, money, page


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("first,rollback", [(0, False), (1, False), (0, True)],
                         ids=["a-wins", "b-wins", "a-rolls-back-b-wins"])
def test_qa03_two_live_multi_room_confirmations(settings, employee, admin_api, guest, room, today, first, rollback):
    a, b, shared = room(), room(), room()
    companions = [a.pk, b.pk]
    start = today + timedelta(days=6)
    reservations = [
        create(admin_api, "reservations", booking(guest().pk, [sibling, shared.pk], start, confirm=False))["id"]
        for sibling in companions
    ]
    assert not RoomClaim.objects.filter(blocking=True).exists()
    interval = {"arrival": start.isoformat(), "departure": (start + timedelta(days=2)).isoformat()}
    assert {r["id"] for r in page(admin_api, "rooms/availability", interval)["results"]} == {a.pk, b.pk, shared.pk}
    specs = [(f"reservations/{rid}/confirm", {}) for rid in reservations]
    second = 1 - first
    desks = [employee("Receptionist"), employee("Receptionist")]
    incumbent, challenger = overlap(settings, (desks[first], desks[second]), specs[first], specs[second], rollback_first=rollback)

    # In the rollback case the first response is tentative: the outer DB transaction was lost.
    assert expect(incumbent, 200).json()["status"] == "confirmed"
    if rollback:
        assert expect(challenger, 200).json()["status"] == "confirmed"
    else:
        expect(challenger, 409)
    winner = second if rollback else first
    loser = 1 - winner
    assert Reservation.objects.get(pk=reservations[winner]).status == "confirmed"
    assert Reservation.objects.get(pk=reservations[loser]).status == "pending"
    assert set(RoomClaim.objects.filter(blocking=True).values_list("reservation_id", "room_id")) == {
        (reservations[winner], shared.pk), (reservations[winner], companions[winner]),
    }
    assert RoomClaim.objects.filter(room=shared, blocking=True).count() == 1
    assert not ReservationEvent.objects.filter(reservation_id=reservations[loser], status="confirmed").exists()
    assert ReservationEvent.objects.filter(reservation_id=reservations[winner], status="confirmed").count() == 1
    assert AuditEvent.objects.filter(actor=desks[winner], object_id=reservations[winner], entity=Reservation._meta.label_lower).exists()
    assert not AuditEvent.objects.filter(actor=desks[loser], object_id=reservations[loser], entity=Reservation._meta.label_lower).exists()
    assert {r["id"] for r in page(admin_api, "rooms/availability", interval)["results"]} == {companions[loser]}


def test_simultaneous_settlement_retries_issue_one_receipt(settings, employee, admin_api, open_stay):
    stay = open_stay()
    payment = (f"invoices/{stay.invoice_id}/payments", {
        "amount": "4000.00", "method": "cash", "reference": "QA-CONCURRENT-TENDER",
    })
    cashier = employee("Accountant")
    responses = overlap(settings, (cashier, cashier), payment, payment)
    a, b = [expect(r, 200, 201).json() for r in responses]
    assert a["id"] == b["id"] and a["receipt_number"] and a["receipt_number"] == b["receipt_number"]
    saved = Payment.objects.get()
    assert saved.pk == a["id"] and saved.invoice_id == stay.invoice_id and saved.amount == Decimal("4000.00")
    assert saved.received_by_id == cashier.pk
    money(get(admin_api, f"invoices/{stay.invoice_id}"), "4000.00", "4000.00", "0.00")


@pytest.mark.parametrize("same", ["space", "vehicle"])
def test_only_one_active_allocation_per_space_and_vehicle(settings, employee, admin_api, guest, same):
    spaces = [create(admin_api, "parking-spaces", {"code": f"QA-P{n}", "is_active": True})["id"] for n in (1, 2)]
    vehicles = [create(admin_api, "vehicles", {"guest": guest().pk, "plate": f"QA{n}TEST"})["id"] for n in (1, 2)]
    rival = {"space": spaces[0 if same == "space" else 1], "vehicle": vehicles[0 if same == "vehicle" else 1]}
    staff = (employee("Receptionist"), employee("Receptionist"))
    first, second = overlap(settings, staff,
                            ("parking-allocations", {"space": spaces[0], "vehicle": vehicles[0]}),
                            ("parking-allocations", rival))
    expect(first, 201)
    expect(second, 409)
    allocation = Allocation.objects.get(ended_at__isnull=True)
    assert (allocation.space_id, allocation.vehicle_id) == (spaces[0], vehicles[0])
    assert action(admin_api, f"parking-allocations/{allocation.pk}/release")["ended_at"]
    assert create(admin_api, "parking-allocations", rival)["id"] != allocation.pk
    assert Allocation.objects.filter(ended_at__isnull=False).count() == 1


@pytest.mark.parametrize("first_command", ["order", "checkout"])
def test_new_order_and_checkout_cannot_both_commit(settings, employee, admin_api, open_stay, first_command):
    stay = open_stay()
    action(admin_api, f"invoices/{stay.invoice_id}/payments", {
        "amount": "4000.00", "method": "cash", "reference": "QA-PRE-CLOSURE-TENDER",
    })
    create_order = ("orders", {"reservation": stay.reservation_id, "room": stay.room_id,
                               "items": [{"menu_item": food(admin_api)["id"], "quantity": 1}]})
    checkout = (f"reservations/{stay.reservation_id}/check_out", {})
    order_first = first_command == "order"
    contenders = (create_order, checkout) if order_first else (checkout, create_order)
    kitchen, desk = employee("Restaurant Staff"), employee("Receptionist")
    actors = (kitchen, desk) if order_first else (desk, kitchen)
    first, second = overlap(settings, actors, *contenders)
    expect(first, 201 if order_first else 200)
    expect(second, 409)
    assert Reservation.objects.get(pk=stay.reservation_id).status == ("checked_in" if order_first else "checked_out")
    assert (Invoice.objects.get(pk=stay.invoice_id).closed_at is None) == order_first
    assert CleaningTask.objects.filter(room_id=stay.room_id).count() == (0 if order_first else 1)
    assert Order.objects.filter(reservation_id=stay.reservation_id).count() == (1 if order_first else 0)
    money(get(admin_api, f"invoices/{stay.invoice_id}"), "4000.00", "4000.00", "0.00")
