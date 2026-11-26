"""QA-07: reject invalid tender, isolate postings and keep an immutable receipt on replay."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch as patch_clock
from zoneinfo import ZoneInfo

import pytest

from apps.billing.models import Invoice, InvoiceItem, Payment

from .support import action, as_user, expect, get, money, request


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("change", [
    {"amount": "0.00"}, {"amount": "-1.00"}, {"amount": "fruit"}, {"amount": "1.001"},
    {"amount": "4000.01"}, {"method": "voucher"}, {"reference": "   "},
], ids=["zero", "negative", "non-numeric", "excess-scale", "over-balance", "unknown-method", "blank-reference"])
def test_qa07_invalid_payment_has_no_receipt_or_balance_change(employee, open_stay, change):
    stay = open_stay()
    office = as_user(employee("Accountant"))
    path = f"invoices/{stay.invoice_id}"
    data = {"amount": "1.00", "method": "cash", "reference": "QA-INVALID", **change}
    response = request(office, "post", f"{path}/payments", data)
    allowed_codes = (400, 409) if change == {"amount": "4000.01"} else (400,)
    expect(response, *allowed_codes)
    assert not Payment.objects.exists()
    detail = get(office, path)
    money(detail, "4000.00", "0.00", "4000.00")
    assert detail["payments"] == []


def test_payment_replay_payload_and_invoice_must_match_even_after_close(admin_api, employee, open_stay):
    first, second = open_stay(), open_stay()
    cashier = employee("Accountant")
    office = as_user(cashier)
    path = f"invoices/{first.invoice_id}/payments"
    evidence = {"amount": "4000.00", "method": "mobile_money", "reference": "QA-FIXTURE-TENDER-A"}
    for unauthorized in ("Restaurant Staff", "Receptionist"):
        expect(request(as_user(employee(unauthorized)), "post", path, evidence), 403)
    assert not Payment.objects.exists()

    original = action(office, path, evidence)
    assert original["receipt_number"] and original["reference"] == evidence["reference"]
    rid = original["id"]
    for update in ({"amount": "1000.00"}, {"method": "bank"}):
        expect(request(office, "post", path, {**evidence, **update}), 409)
    expect(request(office, "post", f"invoices/{second.invoice_id}/payments", evidence), 409)
    assert action(admin_api, f"reservations/{first.reservation_id}/check_out")["status"] == "checked_out"
    replay = action(office, path, evidence)
    assert (replay["id"], replay["receipt_number"]) == (rid, original["receipt_number"])
    assert get(office, f"payments/{rid}")["receipt_number"] == original["receipt_number"]
    saved = Payment.objects.get()
    assert (saved.pk, saved.amount, saved.invoice_id, saved.received_by_id) == (rid, Decimal("4000.00"), first.invoice_id, cashier.pk)
    money(get(office, f"invoices/{second.invoice_id}"), "4000.00", "0.00", "4000.00")


def test_reception_folio_lookup_does_not_open_an_unfiltered_finance_register(employee, open_stay):
    first, second = open_stay(), open_stay()
    desk = as_user(employee("Receptionist"))
    office = as_user(employee("Accountant"))
    # Direct front-desk lookup of a guest folio is permitted.
    assert get(desk, f"invoices/{first.invoice_id}")["reservation"] == first.reservation_id
    register = get(office, "invoices")
    assert {row["id"] for row in register["results"]} == {first.invoice_id, second.invoice_id}
    # "Folio lookups only" is distinct from enumerating every stay's paid amount and balance.
    # A required lookup parameter, denial, or non-disclosing empty result all preserve that boundary.
    broad = expect(request(desk, "get", "invoices"), 200, 400, 403)
    if broad.status_code == 200:
        assert broad.json()["count"] == 0 and broad.json()["results"] == [], (
            "A Receptionist can enumerate unrelated guest folios and balances without selecting a folio."
        )


def test_additional_charge_idempotency_is_not_a_payment(employee, open_stay):
    stay = open_stay()
    office = as_user(employee("Accountant"))
    path = f"invoices/{stay.invoice_id}"
    extra = {"description": "QA laundry", "quantity": 2, "unit_price": "125.05", "reference": "QA-LAUNDRY"}
    before = InvoiceItem.objects.filter(invoice_id=stay.invoice_id).count()
    action(office, f"{path}/charges", extra)
    action(office, f"{path}/charges", extra)
    expect(request(office, "post", f"{path}/charges", {**extra, "quantity": 3}), 409)
    assert InvoiceItem.objects.filter(invoice_id=stay.invoice_id).count() == before + 1
    money(get(office, path), "4250.10", "0.00", "4250.10")
    assert not Payment.objects.exists()


def test_dashboard_counts_postings_by_nairobi_day_not_invoice_creation(employee, today):
    cashier = employee("Accountant")
    office = as_user(cashier)
    midnight = datetime.combine(today, time.min, tzinfo=ZoneInfo("Africa/Nairobi"))
    previous = midnight - timedelta(seconds=1)
    # A previous-day standalone folio already has a posted line and a real tender fixture.
    # Set the fixture clock *before* posting; never edit an immutable charge or payment afterwards.
    with patch_clock("django.utils.timezone.now", return_value=previous):
        old = Invoice.objects.create()
        InvoiceItem.objects.create(invoice=old, description="QA earlier service", quantity=1,
                                   unit_price=Decimal("4000.00"), source_key="qa:previous:line")
        Payment.objects.create(invoice=old, received_by=cashier, amount=Decimal("100.00"),
                               method="cash", reference="QA-PREVIOUS-TENDER")
    before = get(office, "dashboard")["metrics"]
    assert (before["billed"], before["collected"]) == ("0.00", "0.00")

    # Place today's events just inside the boundary (both still yesterday in UTC).
    with patch_clock("django.utils.timezone.now", return_value=midnight):
        action(office, f"invoices/{old.pk}/charges", {
            "description": "QA new service", "quantity": 1, "unit_price": "850.25", "reference": "QA-NEW-EXTRA",
        })
        action(office, f"invoices/{old.pk}/payments", {
            "amount": "2000.00", "method": "cash", "reference": "QA-NEW-TENDER",
        })
    dashboard = get(office, "dashboard")
    assert dashboard["date"] == today.isoformat()
    assert (dashboard["metrics"]["billed"], dashboard["metrics"]["collected"]) == ("850.25", "2000.00")
    assert not {"orders", "reservations", "tasks"}.intersection(dashboard)
    money(get(office, f"invoices/{old.pk}"), "4850.25", "2100.00", "2750.25")
