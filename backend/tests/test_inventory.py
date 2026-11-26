"""QA-01, 02, 04, 08 and 09: identity, calendar boundaries, rollback and lifecycle."""

from datetime import datetime, time, timedelta
from unittest.mock import patch as patch_clock
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, connection, transaction

from apps.billing.models import Invoice, Payment
from apps.housekeeping.models import CleaningTask, MaintenanceRequest
from apps.lodging.models import Guest, Reservation, ReservationEvent, RoomClaim

from .support import action, booking, create, expect, get, page, request


pytestmark = pytest.mark.django_db


def test_qa01_duplicate_guest_keys_not_duplicate_names(admin_api, room, today):
    first = {"full_name": "QA Same Name", "reference": "QA-ONE", "email": "  One@Example.Invalid  "}
    a = create(admin_api, "guests", first)
    assert Guest.objects.get(pk=a["id"]).email == "one@example.invalid"
    for duplicate in (
        {**first, "email": "other@example.invalid"},
        {**first, "reference": "QA-TWO", "email": "one@example.invalid"},
    ):
        expect(request(admin_api, "post", "guests", duplicate), 400, 409)
        assert list(Guest.objects.values_list("id", "reference")) == [(a["id"], "QA-ONE")]

    b = create(admin_api, "guests", {"full_name": first["full_name"], "email": "two@example.invalid", "reference": ""})
    assert b["id"] != a["id"] and b["reference"] and b["reference"] != a["reference"]
    assert Guest.objects.filter(full_name=first["full_name"]).count() == 2
    ids = [create(admin_api, "reservations", booking(profile["id"], [room().pk], today))["id"] for profile in (a, b)]
    for profile, rid in zip((a, b), ids):
        assert [r["id"] for r in get(admin_api, f"guests/{profile['id']}/history")["reservations"]] == [rid]


def available_ids(client, start, end):
    result = page(client, "rooms/availability", {"arrival": start.isoformat(), "departure": end.isoformat()})
    return {r["id"] for r in result["results"]}


def test_qa02_overlapping_multi_room_create_is_atomic_but_touching_nights_fit(admin_api, guest, room, today):
    a, sibling, person = room(), room(), guest()
    start = today + timedelta(days=7)
    end = start + timedelta(days=2)
    booked = create(admin_api, "reservations", booking(person.pk, [a.pk], start))
    assert booked["status"] == "confirmed"
    assert a.pk not in available_ids(admin_api, end - timedelta(days=1), end)
    assert a.pk in available_ids(admin_api, end, end + timedelta(days=1))

    expect(request(admin_api, "post", "reservations", booking(person.pk, [sibling.pk, a.pk], start)), 409)
    assert list(Reservation.objects.values_list("pk", flat=True)) == [booked["id"]]
    assert list(RoomClaim.objects.values_list("reservation_id", "room_id", "blocking")) == [
        (booked["id"], a.pk, True)
    ]
    assert sibling.pk in available_ids(admin_api, start, end)

    adjacent = create(admin_api, "reservations", booking(person.pk, [a.pk], end, nights=1))
    assert adjacent["id"] != booked["id"]
    assert RoomClaim.objects.filter(room=a, blocking=True).count() == 2


def test_conflicting_amendment_keeps_old_claims_dates_and_history(admin_api, guest, room, today):
    taken, original, spare, person = room(), room(), room(), guest()
    start = today + timedelta(days=7)
    create(admin_api, "reservations", booking(person.pk, [taken.pk], start))
    original_booking = create(admin_api, "reservations", booking(person.pk, [original.pk], start))
    rid = original_booking["id"]
    before = list(ReservationEvent.objects.filter(reservation_id=rid).values_list("id", flat=True))

    proposed = booking(person.pk, [spare.pk, taken.pk], start + timedelta(days=1))
    expect(request(admin_api, "patch", f"reservations/{rid}", proposed), 409)

    saved = get(admin_api, f"reservations/{rid}")
    assert saved["arrival"] == start.isoformat() and saved["departure"] == original_booking["departure"]
    assert saved["status"] == "confirmed" and [r["id"] for r in saved["rooms"]] == [original.pk]
    assert list(RoomClaim.objects.filter(reservation_id=rid, blocking=True).values_list("room_id", flat=True)) == [original.pk]
    assert not RoomClaim.objects.filter(room=spare).exists()
    assert list(ReservationEvent.objects.filter(reservation_id=rid).values_list("id", flat=True)) == before


@pytest.mark.parametrize("case", ["missing_arrival", "missing_departure", "equal", "reversed", "no_rooms"])
def test_qa04_invalid_input_leaves_no_booking_history_or_claim(admin_api, guest, room, today, case):
    data = booking(guest().pk, [room().pk], today + timedelta(days=5))
    if case.startswith("missing_"):
        del data[case.removeprefix("missing_")]
    elif case == "no_rooms":
        data["room_ids"] = []
    else:
        data["departure"] = data["arrival"] if case == "equal" else (today + timedelta(days=4)).isoformat()
    expect(request(admin_api, "post", "reservations", data), 400)
    assert not Reservation.objects.exists()
    assert not RoomClaim.objects.exists()
    assert not ReservationEvent.objects.exists()


def test_postgresql_itself_excludes_overlapping_blocking_claims(admin_api, guest, room, today):
    """A read/check in an API handler is not a substitute for the database rule."""
    data = booking(guest().pk, [room().pk], today + timedelta(days=4))
    create(admin_api, "reservations", data)
    draft = create(admin_api, "reservations", {**data, "confirm": False})
    claim = RoomClaim.objects.get(reservation_id=draft["id"])
    assert claim.blocking is False
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        RoomClaim.objects.filter(pk=claim.pk).update(blocking=True)
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert error.value.__cause__.sqlstate == "23P01"  # exclusion_violation, not a different constraint
    claim.refresh_from_db()
    assert claim.blocking is False


def test_blocking_repair_uses_same_calendar_until_resolved(admin_api, guest, room, today):
    bed, person = room(), guest()
    start, end = today + timedelta(days=3), today + timedelta(days=5)
    repair = create(admin_api, "maintenance", {
        "room": bed.pk, "description": "Synthetic blocked window", "start": start.isoformat(),
        "end": end.isoformat(), "blocking": True,
    })
    expect(request(admin_api, "post", "reservations", booking(person.pk, [bed.pk], start)), 409)
    assert not Reservation.objects.exists()
    assert RoomClaim.objects.filter(room=bed, maintenance_id=repair["id"], blocking=True).count() == 1
    assert bed.pk not in available_ids(admin_api, start, end)

    action(admin_api, f"maintenance/{repair['id']}/resolve")
    assert MaintenanceRequest.objects.get(pk=repair["id"]).status == "resolved"
    assert bed.pk in available_ids(admin_api, start, end)
    assert create(admin_api, "reservations", booking(person.pk, [bed.pk], start))["status"] == "confirmed"


def test_qa08_cancel_releases_room_but_forbids_admission(admin_api, guest, room, today):
    bed, person = room(), guest()
    reservation = create(admin_api, "reservations", booking(person.pk, [bed.pk], today))
    rid = reservation["id"]
    assert action(admin_api, f"reservations/{rid}/cancel")["status"] == "cancelled"
    expect(request(admin_api, "post", f"reservations/{rid}/check_in", {}), 409)
    assert Reservation.objects.get(pk=rid).checked_in_at is None
    assert get(admin_api, f"reservations/{rid}")["status"] == "cancelled"
    assert not RoomClaim.objects.filter(reservation_id=rid, blocking=True).exists()
    assert not Invoice.objects.exists() and not CleaningTask.objects.exists()
    assert bed.pk in available_ids(admin_api, today, today + timedelta(days=1))
    assert create(admin_api, "reservations", booking(guest().pk, [bed.pk], today))["status"] == "confirmed"


def test_qa09_checkout_before_admission_has_no_side_effects(admin_api, guest, room, today):
    bed = room()
    rid = create(admin_api, "reservations", booking(guest().pk, [bed.pk], today))["id"]
    events_before = ReservationEvent.objects.filter(reservation_id=rid).count()
    expect(request(admin_api, "post", f"reservations/{rid}/check_out", {}), 409)
    saved = Reservation.objects.get(pk=rid)
    assert saved.status == "confirmed" and saved.checked_in_at is None and saved.checked_out_at is None
    assert RoomClaim.objects.get(reservation=saved, room=bed).blocking is True
    bed.refresh_from_db()
    assert bed.cleanliness == "inspected"
    assert ReservationEvent.objects.filter(reservation=saved).count() == events_before
    assert not CleaningTask.objects.exists() and not Invoice.objects.exists() and not Payment.objects.exists()


def test_early_checkout_retains_consumed_prefix_and_full_contract_amount(admin_api, guest, room, today):
    start = today - timedelta(days=1)
    bed = room(rate="100.00")
    with patch_clock("django.utils.timezone.now", return_value=datetime.combine(start, time(11), ZoneInfo("Africa/Nairobi"))):
        rid = create(admin_api, "reservations", booking(guest().pk, [bed.pk], start, nights=3))["id"]
        action(admin_api, f"reservations/{rid}/check_in")
    invoice = Invoice.objects.get(reservation_id=rid)
    action(admin_api, f"invoices/{invoice.pk}/payments", {
        "amount": "300.00", "method": "cash", "reference": "QA-EARLY-DEPARTURE",
    })
    action(admin_api, f"reservations/{rid}/check_out")
    assert list(RoomClaim.objects.filter(reservation_id=rid, blocking=True).values_list("room_id", "start", "end")) == [
        (bed.pk, start, today),
    ]
    assert Reservation.objects.get(pk=rid).departure == start + timedelta(days=3)
    assert bed.pk in available_ids(admin_api, today, today + timedelta(days=1))
    assert get(admin_api, f"invoices/{invoice.pk}")["total"] == "300.00" and Payment.objects.count() == 1
