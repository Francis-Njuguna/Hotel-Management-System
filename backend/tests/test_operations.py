"""QA-10/11: assignments, room-service eligibility and all-or-nothing posting."""

from datetime import timedelta

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.core.models import AuditEvent
from apps.housekeeping.models import CleaningTask
from apps.lodging.models import Guest, Reservation, Room, RoomClaim
from apps.parking.models import Allocation, Vehicle
from apps.restaurant.models import Order, OrderItem

from .support import action, as_user, booking, create, expect, food, get, money, page, patch, request


pytestmark = pytest.mark.django_db


def test_qa10_assignee_disabled_after_selection_is_revalidated_on_save(admin_api, employee, room):
    manager = as_user(employee("Hotel Manager"))
    worker = employee("Housekeeping Staff")
    signed_in = APIClient()
    signed_in.force_login(worker)
    selected = page(manager, "staff/assignees", {"role": "Housekeeping Staff"})["results"]
    assert [s["id"] for s in selected] == [worker.pk]
    assert set(selected[0]) == {"id", "full_name", "username"}
    earlier = create(manager, "cleaning-tasks", {"room": room().pk, "assignee": worker.pk})
    action(signed_in, f"cleaning-tasks/{earlier['id']}/transition", {"status": "in_progress"})
    audit_ids = set(AuditEvent.objects.filter(actor=worker).values_list("id", flat=True))
    assert audit_ids, "the first accepted work transition should retain its actor"
    bed = room()
    task = create(manager, "cleaning-tasks", {"room": bed.pk, "notes": "QA dispatch"})

    assert patch(admin_api, f"staff/{worker.pk}", {"is_active": False})["is_active"] is False
    expect(request(manager, "post", f"cleaning-tasks/{task['id']}/transition", {
        "status": "assigned", "assignee": worker.pk,
    }), 400, 409)
    saved = CleaningTask.objects.get(pk=task["id"])
    assert saved.status == "pending" and saved.assignee_id is None
    expect(request(manager, "post", "cleaning-tasks", {"room": room().pk, "assignee": worker.pk}), 400, 409)
    assert CleaningTask.objects.count() == 2
    assert CleaningTask.objects.get(pk=earlier["id"]).assignee_id == worker.pk
    assert set(AuditEvent.objects.filter(actor=worker).values_list("id", flat=True)) >= audit_ids
    assert worker.pk not in {s["id"] for s in page(manager, "staff/assignees", {"role": "Housekeeping Staff"})["results"]}
    expect(request(signed_in, "get", "cleaning-tasks"), 403)


def test_qa11_withdrawn_item_is_rechecked_and_mixed_order_is_atomic(employee, admin_api, open_stay):
    stay = open_stay()
    kitchen = as_user(employee("Restaurant Staff"))
    a, b = food(kitchen, "QA available"), food(kitchen, "QA withdrawn")
    assert {r["id"] for r in page(kitchen, "menu-items")["results"] if r["available"]} == {a["id"], b["id"]}
    payload = {"reservation": stay.reservation_id, "room": stay.room_id,
               "items": [{"menu_item": a["id"], "quantity": 1}, {"menu_item": b["id"], "quantity": 2}]}
    assert patch(kitchen, f"menu-items/{b['id']}", {"available": False})["available"] is False
    before = set(InvoiceItem.objects.values_list("id", flat=True))
    expect(request(kitchen, "post", "orders", payload), 400, 409)
    assert not Order.objects.exists() and not OrderItem.objects.exists()
    assert set(InvoiceItem.objects.values_list("id", flat=True)) == before
    assert Invoice.objects.count() == 1 and not Payment.objects.exists()

    # Positive control: identical active stay/role/room with only the still-valid item works.
    order = create(kitchen, "orders", {**payload, "items": payload["items"][:1]})
    assert order["status"] == "pending" and len(order["items"]) == 1
    money(get(admin_api, f"invoices/{stay.invoice_id}"), "4000.00", "0.00", "4000.00")


def test_room_service_requires_a_room_in_this_multi_room_stay(admin_api, employee, guest, room, today):
    rooms = [room(), room(), room()]
    person = guest()
    rid = create(admin_api, "reservations", booking(person.pk, [r.pk for r in rooms[:2]], today))["id"]
    kitchen = as_user(employee("Restaurant Staff"))
    item = food(kitchen)
    payload = {"reservation": rid, "items": [{"menu_item": item["id"], "quantity": 1}]}
    expect(request(kitchen, "post", "orders", {**payload, "room": rooms[0].pk}), 400, 409)
    action(admin_api, f"reservations/{rid}/check_in")
    stay_feed = page(kitchen, "orders/stays")["results"]
    assert [row["id"] for row in stay_feed] == [rid]
    assert not {"guest", "guest_name", "email", "phone", "payments"}.intersection(stay_feed[0])
    assert {r["id"] for r in stay_feed[0]["rooms"]} == {r.pk for r in rooms[:2]}
    assert all("nightly_rate" not in row for row in stay_feed[0]["rooms"])
    expect(request(kitchen, "post", "orders", payload), 400, 409)
    expect(request(kitchen, "post", "orders", {**payload, "room": rooms[2].pk}), 400, 409)
    assert not Order.objects.exists() and not OrderItem.objects.exists()
    order = create(kitchen, "orders", {**payload, "room": rooms[1].pk})
    assert order["room"] == rooms[1].pk and order["reservation"] == rid


def test_qa11_failure_during_charge_rolls_back_serving_and_posting(admin_api, employee, open_stay):
    stay = open_stay()
    kitchen = as_user(employee("Restaurant Staff"))
    item = food(kitchen)
    order = create(kitchen, "orders", {"reservation": stay.reservation_id, "room": stay.room_id,
                                       "items": [{"menu_item": item["id"], "quantity": 1}]})
    path = f"orders/{order['id']}/transition"
    for status in ("confirmed", "preparing", "ready"):
        assert action(kitchen, path, {"status": status})["status"] == status
    before = set(InvoiceItem.objects.values_list("id", flat=True))
    hit = []

    def fail_after_real_insert(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.lstrip().upper().startswith("INSERT INTO") and InvoiceItem._meta.db_table in sql:
            hit.append(True)
            raise RuntimeError("QA fault after the real invoice line insert")
        return result

    kitchen.raise_request_exception = False
    with connection.execute_wrapper(fail_after_real_insert):
        failed = request(kitchen, "post", path, {"status": "served"})
    assert hit and failed.status_code >= 400
    assert Order.objects.get(pk=order["id"]).status == "ready"
    assert set(InvoiceItem.objects.values_list("id", flat=True)) == before
    assert action(kitchen, path, {"status": "served"})["status"] == "served"
    money(get(admin_api, f"invoices/{stay.invoice_id}"), "4850.25", "0.00", "4850.25")


def test_dine_in_creates_one_standalone_invoice_not_a_stay_or_payment(employee):
    kitchen = as_user(employee("Restaurant Staff"))
    office = as_user(employee("Accountant"))
    meal = food(kitchen, price="325.05")
    order = create(kitchen, "orders", {"items": [{"menu_item": meal["id"], "quantity": 2}]})
    assert not Invoice.objects.exists()
    path = f"orders/{order['id']}/transition"
    for status in ("confirmed", "preparing", "ready", "served", "served"):
        assert action(kitchen, path, {"status": status})["status"] == status
    invoice = Invoice.objects.get()
    assert invoice.reservation_id is None
    assert not Reservation.objects.exists() and not Guest.objects.exists() and not Payment.objects.exists()
    money(get(office, f"invoices/{invoice.pk}"), "650.10", "0.00", "650.10")

    # Reception's folio lookup grant is not a department-wide dine-in billing directory.
    reception = as_user(employee("Receptionist"))
    expect(request(reception, "get", f"invoices/{invoice.pk}"), 403, 404)
    listing = expect(request(reception, "get", "invoices"), 200, 403)
    if listing.status_code == 200:
        assert listing.json()["count"] == 0 and listing.json()["results"] == []
    receipt = action(office, f"invoices/{invoice.pk}/payments", {
        "amount": "650.10", "method": "cash", "reference": "QA-RESTAURANT-TENDER",
    })
    expect(request(reception, "get", f"invoices/{invoice.pk}/payments"), 403, 404)
    expect(request(reception, "get", f"payments/{receipt['id']}"), 403, 404)
    expect(request(reception, "get", "payments"), 403)


def test_vehicle_identity_and_inactive_space(employee, guest):
    desk = as_user(employee("Receptionist"))
    person = guest()
    vehicle = create(desk, "vehicles", {"guest": person.pk, "plate": " qa 101 Test "})
    assert vehicle["plate"] == "QA101TEST"
    expect(request(desk, "post", "vehicles", {"guest": guest().pk, "plate": "QA101TEST"}), 400, 409)
    assert Vehicle.objects.get().pk == vehicle["id"]
    space = create(desk, "parking-spaces", {"code": "QA-OFFLINE", "is_active": False})
    expect(request(desk, "post", "parking-allocations", {"space": space["id"], "vehicle": vehicle["id"]}), 409)
    assert not Allocation.objects.exists()


@pytest.mark.parametrize("reason", ["occupied", "repair"])
def test_manager_inspection_cannot_override_occupancy_or_current_block(admin_api, open_stay, room, employee, today, reason):
    if reason == "occupied":
        bed = Room.objects.get(pk=open_stay().room_id)
    else:
        bed = room()
        create(admin_api, "maintenance", {"room": bed.pk, "description": "QA current block", "blocking": True,
                                         "start": today.isoformat(), "end": (today + timedelta(days=1)).isoformat()})
    cleaner = employee("Housekeeping Staff")
    task = create(admin_api, "cleaning-tasks", {"room": bed.pk, "assignee": cleaner.pk})
    path = f"cleaning-tasks/{task['id']}/transition"
    for status in ("in_progress", "completed"):
        action(as_user(cleaner), path, {"status": status})
    expect(request(admin_api, "post", path, {"status": "inspected"}), 409)
    assert CleaningTask.objects.get(pk=task["id"]).status == "completed"
    bed.refresh_from_db()
    assert bed.cleanliness == "dirty"
    state = get(admin_api, f"rooms/{bed.pk}")
    assert (state["occupied"], state["maintenance"]) == (reason == "occupied", reason == "repair")


def test_one_dirty_room_prevents_the_entire_multi_room_admission(admin_api, guest, room, today):
    ready, dirty = room(), room()
    rid = create(admin_api, "reservations", booking(guest().pk, [ready.pk, dirty.pk], today))["id"]
    create(admin_api, "cleaning-tasks", {"room": dirty.pk})
    expect(request(admin_api, "post", f"reservations/{rid}/check_in", {}), 409)
    saved = Reservation.objects.get(pk=rid)
    assert saved.status == "confirmed" and saved.checked_in_at is None
    assert RoomClaim.objects.filter(reservation=saved, blocking=True).count() == 2
    assert not Invoice.objects.exists() and not InvoiceItem.objects.exists()
    assert not any(r["occupied"] for r in page(admin_api, "rooms")["results"])
