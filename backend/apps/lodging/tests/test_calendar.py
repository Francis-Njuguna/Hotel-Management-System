from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.lodging.models import Guest, Reservation, ReservationEvent, RoomClaim


pytestmark = pytest.mark.django_db


def test_availability_is_paginated_sellable_nights_not_current_readiness(desk, room, book, clock):
    occupied, repair, dirty, inactive = [room() for _ in range(4)]
    room(category="Single")
    desk("patch", f"rooms/{inactive['id']}", {"is_active": False})
    stay = book([occupied["id"]], nights=1)
    desk("post", f"reservations/{stay['id']}/check_in")
    tomorrow = clock.day + timedelta(days=1)
    desk("post", "maintenance", {"room": repair["id"], "start": clock.day, "end": tomorrow,
                                 "blocking": True, "description": "Synthetic one-night closure"}, expect=201)
    desk("post", "cleaning-tasks", {"room": dirty["id"]}, expect=201)

    today = {"arrival": clock.day, "departure": tomorrow, "category": "Double"}
    current = desk("get", "rooms/availability", today)
    assert current["count"] == 1 and current["results"][0]["id"] == dirty["id"]
    assert current["results"][0]["cleanliness"] == "dirty"
    following = {"arrival": tomorrow, "departure": tomorrow + timedelta(days=1), "category": "Double", "page_size": 1}
    pages = [desk("get", "rooms/availability", {**following, "page": n}) for n in (1, 2, 3)]
    assert pages[0]["previous"] is None and pages[0]["next"] and pages[-1]["next"] is None
    assert all(page["count"] == 3 and len(page["results"]) == 1 for page in pages)
    flags = {r["id"]: (r["occupied"], r["maintenance"], r["cleanliness"]) for page in pages for r in page["results"]}
    assert flags == {occupied["id"]: (True, False, "inspected"), repair["id"]: (False, True, "inspected"),
                     dirty["id"]: (False, False, "dirty")}
    for invalid in ({"arrival": clock.day}, {"arrival": tomorrow, "departure": clock.day}, {"arrival": clock.day, "departure": clock.day}):
        desk("get", "rooms/availability", invalid, expect=400)


def test_group_confirmation_and_amendment_preserve_or_commit_the_entire_plan(desk, room, book, clock):
    a, b, c, spare = room("100.25"), room("200.50"), room("300.75"), room()
    arrival = clock.day + timedelta(days=3)
    draft = book([a["id"], b["id"]], arrival=arrival, confirm=False)
    rid = draft["id"]
    blocker = book([b["id"]], arrival=arrival)
    original = list(RoomClaim.objects.filter(reservation_id=rid).order_by("pk").values())
    events = ReservationEvent.objects.filter(reservation_id=rid)
    desk("post", f"reservations/{rid}/confirm", expect=409)
    assert list(RoomClaim.objects.filter(reservation_id=rid).order_by("pk").values()) == original
    assert events.count() == 1 and not any(row["blocking"] for row in original)

    desk("post", f"reservations/{blocker['id']}/cancel")
    desk("patch", f"rooms/{a['id']}", {"nightly_rate": "999.00"})
    desk("patch", f"rooms/{c['id']}", {"nightly_rate": "333.33"})
    committed = desk("post", f"reservations/{rid}/confirm")
    assert committed["status"] == "confirmed" and events.count() == 2
    assert {r["id"]: r["nightly_rate"] for r in committed["rooms"]} == {a["id"]: "100.25", b["id"]: "200.50"}
    changed = desk("patch", f"reservations/{rid}", {"room_ids": [c["id"], a["id"]]})
    assert changed["status"] == "confirmed" and events.count() == 3
    assert {r["id"]: r["nightly_rate"] for r in changed["rooms"]} == {a["id"]: "100.25", c["id"]: "333.33"}
    kept = RoomClaim.objects.get(reservation_id=rid, room_id=a["id"])
    assert kept.blocking and kept.pk == next(row["id"] for row in original if row["room_id"] == a["id"])
    assert not RoomClaim.objects.filter(reservation_id=rid, room_id=b["id"]).exists()

    # A competing committed closure on just one of the new rooms must preserve
    # the original sold rooms, rates, guest, dates and event history.
    desk("post", "maintenance", {"room": b["id"], "start": arrival, "end": arrival + timedelta(days=3),
                                 "blocking": True, "description": "Synthetic maintenance"}, expect=201)
    before = desk("get", f"reservations/{rid}")
    desk("patch", f"reservations/{rid}", {"room_ids": [spare["id"], b["id"]], "departure": arrival + timedelta(days=4)}, expect=409)
    assert desk("get", f"reservations/{rid}") == before
    assert not RoomClaim.objects.filter(room_id=spare["id"]).exists()


def test_inputs_cannot_set_workflow_or_smuggle_noninteger_room_ids(desk, guest, room, clock):
    bed = room()
    payload = {"guest": guest["id"], "arrival": clock.day, "departure": clock.day + timedelta(days=1), "room_ids": [bed["id"]]}
    for ids in ([], [True], [str(bed["id"])], [float(bed["id"])], [bed["id"], bed["id"]], [2**63], [2**62]):
        desk("post", "reservations", {**payload, "room_ids": ids}, expect=400)
    for forged in ({"status": "checked_in"}, {"checked_in_at": "2032-06-12T12:00:00Z"}, {"total": "0.00"}):
        desk("post", "reservations", {**payload, **forged}, expect=400)
    assert not Reservation.objects.exists() and not RoomClaim.objects.exists() and not ReservationEvent.objects.exists()


def test_postgresql_rejects_bad_source_windows_and_mixed_booking_maintenance_overlap(room, book, clock):
    from apps.housekeeping.models import MaintenanceRequest

    bed = room()
    sold = book([bed["id"]], nights=2)
    claim = RoomClaim.objects.get(reservation_id=sold["id"])
    work = MaintenanceRequest.objects.create(room_id=bed["id"], start=claim.start, end=claim.end,
                                            description="Synthetic constraint-only fixture", blocking=True)

    def rejects(name, write):
        with pytest.raises(IntegrityError) as error, transaction.atomic():
            write()
        assert error.value.__cause__.diag.constraint_name == name

    row = RoomClaim.objects.filter(pk=claim.pk)
    rejects("lodging_claim_one_source", lambda: row.update(reservation_id=None))
    rejects("lodging_claim_one_source", lambda: row.update(maintenance=work, nightly_rate=Decimal("0.00")))
    rejects("lodging_claim_dates_valid", lambda: row.update(end=claim.start))

    def infinite_end():
        with connection.cursor() as cursor:
            cursor.execute('UPDATE lodging_roomclaim SET "end" = %s::date WHERE id = %s', ("infinity", claim.pk))

    rejects("lodging_claim_dates_valid", infinite_end)
    proposed = dict(room_id=bed["id"], maintenance=work, start=claim.start, end=claim.end)
    rejects("lodging_claim_rate_valid", lambda: RoomClaim.objects.create(**proposed, nightly_rate=Decimal("0.01")))
    rejects("lodging_roomclaim_no_overlap", lambda: RoomClaim.objects.create(**proposed, blocking=True))
    assert row.get().end == clock.day + timedelta(days=2)
    # Predicate is on the claim itself: pending/nonblocking rows may coexist.
    pending = RoomClaim.objects.create(**proposed, blocking=False)
    adjacent = claim.end + timedelta(days=1)
    RoomClaim.objects.filter(pk=pending.pk).update(start=claim.end, end=adjacent, blocking=True)
    assert RoomClaim.objects.filter(room_id=bed["id"], blocking=True).count() == 2

    rejects("lodging_res_actual_times", lambda: Reservation.objects.filter(pk=sold["id"]).update(status="checked_in"))
    rejects("lodging_guest_canonical_email", lambda: Guest.objects.filter(pk=sold["guest"]).update(email="Uncanonical@EXAMPLE.INVALID"))
