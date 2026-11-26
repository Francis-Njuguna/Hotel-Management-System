from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.api import Conflict
from apps.core.models import AuditEvent
from apps.lodging.models import Reservation, RoomClaim
from apps.restaurant.models import MenuItem, Order

from ..models import Invoice, InvoiceItem, Payment
from ..services import close_folio, open_folio, post_charge, post_order, record_payment
from .fixtures import admitted, meal, staff, tender


class LedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.desk = staff("Receptionist")
        cls.cashier = staff("Accountant")
        cls.server = staff("Restaurant Staff")

    def test_folio_uses_booked_nights_and_agreed_claim_rates_once_per_room(self):
        reservation = admitted("1100.10", "50.05", nights=3)
        invoice = open_folio(reservation, self.desk)
        self.assertEqual(open_folio(reservation, self.desk).pk, invoice.pk)
        keys = {f"room:{pk}" for pk in RoomClaim.objects.filter(reservation=reservation).values_list("pk", flat=True)}
        self.assertSetEqual(set(invoice.items.values_list("source_key", flat=True)), keys)
        self.assertCountEqual(invoice.items.values_list("quantity", "unit_price"),
                              [(3, Decimal("1100.10")), (3, Decimal("50.05"))])
        self.assertEqual(invoice.total, Decimal("3450.45"))
        self.assertFalse(invoice.items.filter(created_at__isnull=True).exists())
        self.assertTrue(InvoiceItem._meta.get_field("created_at").db_index)
        self.assertEqual(AuditEvent.objects.filter(verb="billing.folio.open").count(), 1)
        self.assertFalse(Payment.objects.exists())

    def test_served_order_snapshots_each_sold_item_not_current_menu_price(self):
        reservation = admitted("2000.00")
        invoice = open_folio(reservation, self.desk)
        order = meal([("Test soup", 2, "125.05"), ("Test meal", 1, "600.15")], reservation=reservation)
        self.assertEqual(post_order(order, self.server).pk, invoice.pk)
        posted = list(invoice.items.filter(source_key__startswith="order:").values_list(
            "pk", "description", "quantity", "unit_price"))
        self.assertEqual([line[1:] for line in posted], [("Test soup", 2, Decimal("125.05")),
                                                          ("Test meal", 1, Decimal("600.15"))])
        MenuItem.objects.update(name="New menu name", price=Decimal("999.00"), available=False)
        self.assertEqual(post_order(order, self.server).pk, invoice.pk)
        self.assertEqual(list(invoice.items.filter(source_key__startswith="order:")
                              .values_list("pk", "description", "quantity", "unit_price")), posted)
        self.assertEqual(invoice.balance, Decimal("4850.25"))
        self.assertEqual(AuditEvent.objects.filter(verb="billing.order.post").count(), 1)
        self.assertFalse(Payment.objects.exists())

    def test_free_stay_closes_without_tender_and_served_replay_cannot_reopen_it(self):
        stay = admitted("0.00")
        invoice = open_folio(stay, self.desk)
        original = meal([("Synthetic included meal", 1, "0.00")], reservation=stay)
        post_order(original, self.server)
        closed = close_folio(stay, self.desk).closed_at
        self.assertEqual(post_order(original, self.server).pk, invoice.pk)
        later = meal([("Test late order", 1, "1.00")], reservation=stay)
        with self.assertRaises(Conflict):
            post_order(later, self.server)
        invoice.refresh_from_db()
        self.assertEqual(invoice.closed_at, closed)
        self.assertEqual(invoice.items.count(), 2)
        self.assertEqual(invoice.balance, Decimal("0.00"))
        self.assertFalse(Payment.objects.exists())

    def test_dine_in_never_creates_a_stay_payment_or_spare_invoice(self):
        for state in ("pending", "confirmed", "preparing", "cancelled"):
            with self.subTest(state=state), self.assertRaises(Conflict):
                post_order(meal([("Not served", 1, "1.00")], status=state), self.server)
        with self.assertRaises(Conflict):
            post_order(meal([]), self.server)
        self.assertFalse(Invoice.objects.exists())  # all private candidates rolled back
        for _ in range(2):
            order = meal([("Test tea", 2, "0.10"), ("Test bread", 1, "0.07")], status="ready")
            invoice = post_order(order, self.server)
            order.refresh_from_db()
            self.assertEqual(order.status, "served")
            self.assertEqual(post_order(order, self.server).pk, invoice.pk)
            self.assertIsNone(invoice.reservation_id)
            self.assertEqual(invoice.balance, Decimal("0.27"))
        self.assertEqual(Invoice.objects.count(), 2)
        self.assertEqual(InvoiceItem.objects.count(), 4)
        self.assertFalse(Reservation.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_identical_values_are_counted_per_row_and_not_multiplied_by_joins(self):
        reservation = admitted("100.05")
        invoice = open_folio(reservation, self.desk)
        post_charge(invoice, self.cashier, {"description": "Test laundry", "quantity": 2,
                                          "unit_price": "100.05", "reference": "TEST-L1"})
        for ref in ("R1", "R2"):
            record_payment(invoice, self.cashier, tender(ref, "100.10"))
        empty = Invoice.objects.create()
        # Two identical line totals AND two identical tender amounts. SUM DISTINCT is also wrong.
        with self.assertNumQueries(1):
            results = {row.pk: (row.total, row.paid, row.balance) for row in Invoice.objects.with_totals()}
        self.assertEqual(results[invoice.pk], (Decimal("400.20"), Decimal("200.20"), Decimal("200.00")))
        self.assertEqual(results[empty.pk], (Decimal("0.00"),) * 3)

    def test_zero_balance_and_no_open_order_required_no_implicit_payment_or_repricing(self):
        stay = admitted("75.05", nights=4)
        invoice = open_folio(stay, self.desk)
        charge = {"description": "Test article", "quantity": 2, "unit_price": "0.05", "reference": "TEST-C1"}
        original, _ = post_charge(invoice, self.cashier, charge)
        with self.assertRaises(Conflict):
            close_folio(stay, self.desk)
        self.assertFalse(Payment.objects.exists())
        evidence = tender("FULL", "300.30", "mobile_money")
        receipt, _ = record_payment(invoice, self.cashier, evidence)
        pending = meal([("Test obligation", 1, "12.34")], reservation=stay, status="pending")
        with self.assertRaises(Conflict):
            close_folio(stay, self.desk)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.closed_at)
        Order.objects.filter(pk=pending.pk).update(status="cancelled")
        stamp = close_folio(stay, self.desk).closed_at
        self.assertIsNotNone(stamp)
        self.assertEqual(close_folio(stay, self.desk).closed_at, stamp)
        item, new = post_charge(invoice, self.cashier, charge)
        self.assertEqual((item.pk, new), (original.pk, False))
        another_cashier = staff("Accountant")
        replay, new = record_payment(invoice, another_cashier, evidence)
        self.assertEqual((replay.pk, replay.receipt_number, replay.received_by_id, new),
                         (receipt.pk, receipt.receipt_number, self.cashier.pk, False))
        for command, data in [(record_payment, tender("LATE")), (post_charge, {**charge, "reference": "TEST-NEW"}),
                              (record_payment, {**evidence, "method": "bank"}), (post_charge, {**charge, "quantity": 1})]:
            with self.subTest(data=data), self.assertRaises(Conflict):
                command(invoice, self.cashier, data)
        self.assertEqual((invoice.total, invoice.paid, invoice.balance),
                         (Decimal("300.30"), Decimal("300.30"), Decimal("0.00")))
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(verb="billing.folio.close").count(), 1)
        self.assertFalse(AuditEvent.objects.filter(summary__contains=evidence["reference"]).exists())

    def test_an_audit_failure_aborts_the_entire_posting(self):
        order = meal([("Test item", 2, "12.00")], status="ready")
        with patch("apps.billing.services.record", side_effect=RuntimeError("test audit failure")):
            with self.assertRaises(RuntimeError):
                post_order(order, self.server)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(InvoiceItem.objects.exists())
        order.refresh_from_db()
        self.assertEqual(order.status, "ready")
        self.assertFalse(AuditEvent.objects.filter(verb="order.served").exists())
        invoice = post_order(order, self.server)
        evidence = tender("AUDIT-RETRY", "24.00", "bank")
        with patch("apps.billing.services.record", side_effect=RuntimeError("test audit failure")):
            with self.assertRaises(RuntimeError):
                record_payment(invoice, self.cashier, evidence)
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(invoice.balance, Decimal("24.00"))
        self.assertTrue(record_payment(invoice, self.cashier, evidence)[1])

    def test_posted_rows_cannot_be_overwritten_or_deleted_via_orm(self):
        invoice = open_folio(admitted("10.00"), self.desk)
        different = Invoice.objects.create()
        receipt, _ = record_payment(invoice, self.cashier, tender("IMMUTABLE"))
        for obj, column, value in [(receipt, "amount", Decimal("9.00")), (invoice.items.get(), "quantity", 5)]:
            with self.subTest(model=obj._meta.label):
                rows = type(obj).objects.filter(pk=obj.pk)
                setattr(obj, column, value)
                for fn in (obj.save, obj.delete, rows.delete, lambda: rows.update(**{column: value}),
                           lambda: type(obj).objects.bulk_update([obj], [column])):
                    with self.assertRaises(ValidationError):
                        fn()
        with self.assertRaises(ValidationError), transaction.atomic():
            different.payments.add(receipt)
        with self.assertRaises(ValidationError), transaction.atomic():
            different.items.add(invoice.items.get())
        self.assertEqual(invoice.balance, Decimal("19.00"))

    def test_database_constraints_reject_invalid_and_duplicate_entries(self):
        stay = admitted("10.00")
        invoice = open_folio(stay, self.desk)
        item = dict(invoice=invoice, source_key="test:key", description="Synthetic row", quantity=1, unit_price=Decimal("0.00"))
        payment = dict(invoice=invoice, received_by=self.cashier, reference="TEST-CHECK", method="cash", amount=Decimal("0.01"))
        for create, data in [
            (InvoiceItem.objects.create, {**item, "quantity": 0}),
            (InvoiceItem.objects.create, {**item, "unit_price": Decimal("-0.01")}),
            (InvoiceItem.objects.create, {**item, "source_key": " \t"}),
            (Payment.objects.create, {**payment, "amount": Decimal("0.00")}),
            (Payment.objects.create, {**payment, "method": "pending"}),
            (Payment.objects.create, {**payment, "reference": " \t"}),
            (Invoice.objects.create, {"reservation": stay}),
            (Invoice.objects.create, {"closed_at": invoice.created_at - timedelta(days=1)}),
        ]:
            with self.subTest(data=data), self.assertRaises(IntegrityError), transaction.atomic():
                create(**data)
        for create, data in [(InvoiceItem.objects.create, item), (Payment.objects.create, payment)]:
            create(**data)
            with self.assertRaises(IntegrityError), transaction.atomic():
                create(**{**data, "invoice": Invoice.objects.create()})
        for bad in (0.55, Decimal("1.001"), Decimal("NaN")):
            with self.subTest(bad=bad), self.assertRaises(ValidationError), transaction.atomic():
                Payment.objects.create(**{**payment, "amount": bad, "reference": "TEST-PRECISION"})
        with self.assertRaises(ValidationError):
            InvoiceItem.objects.create(**{**item, "source_key": "test:quantity", "quantity": 1.5})
