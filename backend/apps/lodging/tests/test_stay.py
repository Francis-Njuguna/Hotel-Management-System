from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.lodging import services
from apps.lodging.models import Reservation, ReservationEvent, Room, RoomClaim


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("elapsed", [0, 2, 4, 5], ids=["same-day", "unused-tail", "planned-end", "overdue"])
def test_departure_releases_only_unused_nights_and_never_reprices_or_collects(desk, room, book, clock, elapsed):
    from apps.billing.models import Invoice, InvoiceItem, Payment
    from apps.housekeeping.models import CleaningTask

    arrival = clock.day
    end = arrival + timedelta(days=4)
    beds = [room("125.25"), room("99.75")]
    ids = [r["id"] for r in beds]
    stay = book(ids, nights=4)
    path = f"reservations/{stay['id']}"
    desk("patch", f"rooms/{ids[0]}", {"nightly_rate": "666.66"})
    with timezone.override("UTC"):  # it is still the previous day in UTC at this synthetic instant
        checked_in = desk("post", f"{path}/check_in")
    assert checked_in["checked_in_at"] and not checked_in["checked_out_at"]
    folio = Invoice.objects.get(reservation_id=stay["id"])
    assert set(InvoiceItem.objects.filter(invoice=folio).values_list("quantity", "unit_price")) == {
        (4, Decimal("125.25")), (4, Decimal("99.75")),
    }
    clock.day = arrival + timedelta(days=elapsed)
    desk("post", f"{path}/check_out", expect=409)
    assert not Payment.objects.exists() and not CleaningTask.objects.exists()
    folio.refresh_from_db()
    assert folio.closed_at is None and RoomClaim.objects.filter(reservation_id=stay["id"], end=end, blocking=True).count() == 2

    # Two synthetic records of received funds. Neither checkout attempt creates a tender.
    for index in (1, 2):
        desk("post", f"invoices/{folio.pk}/payments", {"amount": "450.00", "method": "cash",
             "reference": f"SYNTHETIC-EARLY-{index}"}, expect=(200, 201))
    result = desk("post", f"{path}/check_out")
    assert result["status"] == "checked_out" and result["departure"] == end.isoformat()
    assert [event["status"] for event in result["events"]] == ["confirmed", "checked_in", "checked_out"]
    prefix_end = end if elapsed == 0 else min(clock.day, end)
    actual = list(RoomClaim.objects.filter(reservation_id=stay["id"]).values_list("start", "end", "blocking"))
    assert actual == [(arrival, prefix_end, elapsed > 0)] * 2
    settled = desk("get", f"invoices/{folio.pk}")
    assert (settled["total"], settled["paid"], settled["balance"]) == ("900.00", "900.00", "0.00") and settled["closed_at"]
    assert set(CleaningTask.objects.values_list("room_id", "status")) == {(pk, "pending") for pk in ids}
    assert Room.objects.filter(pk__in=ids, cleanliness="dirty").count() == 2
    desk("post", f"{path}/check_out", expect=409)
    assert CleaningTask.objects.count() == 2 and Payment.objects.count() == 2


def test_overdue_occupant_and_one_dirty_room_block_entire_adjacent_admission(desk, room, book, clock):
    from apps.billing.models import Invoice

    d = clock.day
    first, second = room("0.00"), room("0.00")
    early = book([first["id"]], nights=1)
    adjacent = book([second["id"], first["id"]], nights=2, arrival=d + timedelta(days=1))
    next_path = f"reservations/{adjacent['id']}"
    desk("post", f"{next_path}/check_in", expect=409)  # too early, even if both rooms physically empty
    desk("post", f"reservations/{early['id']}/check_in")
    clock.day = d + timedelta(days=1)
    desk("post", f"{next_path}/check_in", expect=409)  # adjacent nights, but predecessor still in the room
    assert not Invoice.objects.filter(reservation_id=adjacent["id"]).exists()
    assert not desk("get", f"rooms/{second['id']}")["occupied"]
    assert desk("get", f"rooms/{first['id']}")["occupied"]
    desk("post", f"reservations/{early['id']}/check_out")
    desk("post", f"{next_path}/check_in", expect=409)  # vacancy is not inspection
    assert not Invoice.objects.filter(reservation_id=adjacent["id"]).exists()
    assert Reservation.objects.get(pk=adjacent["id"]).checked_in_at is None
    assert list(ReservationEvent.objects.filter(reservation_id=adjacent["id"]).values_list("status", flat=True)) == ["confirmed"]

    # A different booked date is not an escape hatch once the scheduled arrival has passed.
    clock.day += timedelta(days=1)
    desk("patch", next_path, {"room_ids": [second["id"]]}, expect=409)
    clock.day += timedelta(days=1)
    desk("post", f"{next_path}/check_in", expect=409)  # departure date itself is exclusive
    assert Reservation.objects.get(pk=adjacent["id"]).status == "confirmed"


def test_rollback_after_second_real_turnover_restores_occupancy_folio_tasks_and_audit(
    admin_user, desk, room, book, clock,
):
    from apps.billing.models import Invoice
    from apps.core.models import AuditEvent
    from apps.housekeeping.models import CleaningTask

    ids = [room("0.00")["id"], room("0.00")["id"]]
    rid = book(ids, nights=3)["id"]
    desk("post", f"reservations/{rid}/check_in")
    clock.day += timedelta(days=1)
    audit_before = list(AuditEvent.objects.order_by("pk").values_list("pk", flat=True))
    timeline_before = list(ReservationEvent.objects.order_by("pk").values_list("pk", flat=True))
    plan_before = list(RoomClaim.objects.order_by("pk").values())
    writes = []

    class InjectedFailure(Exception):
        pass

    def fail_after_insert(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.lstrip().upper().startswith("INSERT INTO") and CleaningTask._meta.db_table in sql:
            writes.append(1)
            if len(writes) == len(ids):
                raise InjectedFailure("Synthetic failure after the last real task insert")
        return result

    # No success path is mocked. At this point the folio, checkout instant,
    # shortening and BOTH physical-room/task updates have already been written.
    with connection.execute_wrapper(fail_after_insert), pytest.raises(InjectedFailure):
        services.check_out(rid, admin_user)

    assert len(writes) == 2 and not CleaningTask.objects.exists()
    assert Invoice.objects.get(reservation_id=rid).closed_at is None
    assert Reservation.objects.get(pk=rid).checked_out_at is None
    assert {r["id"] for r in desk("get", "rooms")["results"] if r["occupied"] and r["cleanliness"] == "inspected"} == set(ids)
    assert list(RoomClaim.objects.order_by("pk").values()) == plan_before
    assert list(ReservationEvent.objects.order_by("pk").values_list("pk", flat=True)) == timeline_before
    assert list(AuditEvent.objects.order_by("pk").values_list("pk", flat=True)) == audit_before
    assert desk("post", f"reservations/{rid}/check_out")["status"] == "checked_out"
    assert CleaningTask.objects.count() == 2


def test_failed_folio_posting_does_not_admit_any_room_or_leave_an_invoice(admin_user, desk, room, book):
    from apps.billing.models import Invoice, InvoiceItem

    ids = [room()["id"], room()["id"]]
    rid = book(ids)["id"]

    class PostingFailure(Exception):
        pass

    def fail_after_posting(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.lstrip().upper().startswith("INSERT INTO") and InvoiceItem._meta.db_table in sql:
            raise PostingFailure("Synthetic fault after the actual charge insert")
        return result

    with connection.execute_wrapper(fail_after_posting), pytest.raises(PostingFailure):
        services.check_in(rid, admin_user)
    stay = desk("get", f"reservations/{rid}")
    assert stay["status"] == "confirmed" and stay["checked_in_at"] is None
    assert [e["status"] for e in stay["events"]] == ["confirmed"]
    assert not Invoice.objects.exists() and not InvoiceItem.objects.exists()
    assert not any(r["occupied"] for r in desk("get", "rooms")["results"])
    assert RoomClaim.objects.filter(reservation_id=rid, blocking=True).count() == 2
    assert desk("post", f"reservations/{rid}/check_in")["status"] == "checked_in"
    assert Invoice.objects.count() == 1 and InvoiceItem.objects.count() == 2


def test_an_open_room_order_prevents_checkout_even_with_zero_balance(desk, room, book):
    from apps.billing.models import Invoice, Payment
    from apps.housekeeping.models import CleaningTask

    bed = room("0.00")
    rid = book([bed["id"]])["id"]
    desk("post", f"reservations/{rid}/check_in")
    menu = desk("post", "menu-items", {"name": "Synthetic meal", "category": "Synthetic", "price": "50.25", "available": True}, expect=201)
    order = desk("post", "orders", {"reservation": rid, "room": bed["id"], "items": [{"menu_item": menu["id"], "quantity": 1}]}, expect=201)
    invoice = Invoice.objects.get(reservation_id=rid)
    assert desk("get", f"invoices/{invoice.pk}")["balance"] == "0.00"
    desk("post", f"reservations/{rid}/check_out", expect=409)
    invoice.refresh_from_db()
    assert invoice.closed_at is None and not CleaningTask.objects.exists() and not Payment.objects.exists()
    assert desk("get", f"rooms/{bed['id']}")["occupied"] and not ReservationEvent.objects.filter(status="checked_out").exists()
    desk("post", f"orders/{order['id']}/transition", {"status": "cancelled"})
    assert desk("post", f"reservations/{rid}/check_out")["status"] == "checked_out"
    assert CleaningTask.objects.count() == 1 and not Payment.objects.exists()
