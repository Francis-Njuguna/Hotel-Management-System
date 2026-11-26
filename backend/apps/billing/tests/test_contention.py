"""Two real PostgreSQL connections; barriers schedule real SQL, not simulated writes."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event

from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction
from django.test import TransactionTestCase

from apps.core.api import Conflict
from apps.core.models import AuditEvent
from apps.restaurant.models import Order

from ..models import Invoice, InvoiceItem, Payment
from ..services import post_charge, post_order, record_payment
from .fixtures import meal, staff, tender


def worker(command, sql_hook):
    """The result leaves the thread only after commit/rollback; never share connections."""
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = '20s'")
                cur.execute("SET LOCAL statement_timeout = '30s'")
            with connection.execute_wrapper(sql_hook):
                value = command()
        return "ok", value
    except Conflict:
        return "conflict", None
    finally:
        connections.close_all()


class FinanceContentionTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.cashier = staff("Accountant")
        self.server = staff("Restaurant Staff")

    def invoice(self):
        invoice = Invoice.objects.create()
        post_charge(invoice, self.cashier, {"description": "Synthetic service", "quantity": 1,
                                          "unit_price": "10.00", "reference": "TEST-SLIP"})
        return invoice

    def receive(self, invoice_pk, data):
        user = get_user_model().objects.get(pk=self.cashier.pk)
        receipt, _ = record_payment(Invoice.objects.get(pk=invoice_pk), user, data)
        return receipt.pk

    def simultaneous_inserts(self, model, commands, *, after=False):
        both = Barrier(2, timeout=15)
        prefix = f'INSERT INTO "{model._meta.db_table}" '

        def interleave(execute, sql, params, many, context):
            matches = sql.lstrip().startswith(prefix)
            if matches and not after:
                both.wait()
            result = execute(sql, params, many, context)
            if matches and after:
                both.wait()
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, command, interleave) for command in commands]
            outcomes = [future.result(timeout=40) for future in futures]
        connection.close()  # Reconcile independent committed state.
        return outcomes

    def test_one_global_reference_racing_across_two_different_invoice_locks(self):
        invoices = [self.invoice(), self.invoice()]
        data = tender("GLOBAL-COLLISION", "5.00", "bank")
        outcomes = self.simultaneous_inserts(Payment, [lambda pk=i.pk: self.receive(pk, data) for i in invoices])
        self.assertCountEqual([result for result, _ in outcomes], ["ok", "conflict"])
        only = Payment.objects.get()
        self.assertEqual(only.reference, data["reference"])
        self.assertIn(("ok", only.pk), outcomes)
        self.assertCountEqual([i.balance for i in invoices], [Decimal("5.00"), Decimal("10.00")])
        self.assertEqual(AuditEvent.objects.filter(verb="billing.payment.record").count(), 1)

    def test_competing_dine_in_candidates_leave_one_invoice_one_set_of_lines(self):
        order = meal([("Synthetic tea", 2, "0.10"), ("Synthetic cake", 1, "0.05")], status="ready")

        def serve():
            user = get_user_model().objects.get(pk=self.server.pk)
            return post_order(Order.objects.get(pk=order.pk), user).pk

        # Both private invoice inserts have actually executed BEFORE either can lock the order.
        outcomes = self.simultaneous_inserts(Invoice, [serve, serve], after=True)
        invoice = Invoice.objects.get()
        self.assertEqual(outcomes, [("ok", invoice.pk)] * 2)
        self.assertIsNone(invoice.reservation_id)
        self.assertEqual(invoice.balance, Decimal("0.25"))
        self.assertEqual(InvoiceItem.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(verb="billing.order.post").count(), 1)
        self.assertEqual(AuditEvent.objects.filter(verb="order.served").count(), 1)
        self.assertFalse(Payment.objects.exists())

    def test_later_different_reference_uses_balance_after_commit_or_rollback(self):
        for rollback_first in (False, True):
            with self.subTest(rollback_first=rollback_first), ThreadPoolExecutor(max_workers=1) as pool:
                invoice = self.invoice()
                about_to_lock = Event()

                def witness(execute, sql, params, many, context):
                    if 'FROM "billing_invoice"' in sql and "FOR UPDATE" in sql:
                        about_to_lock.set()
                    return execute(sql, params, many, context)

                with transaction.atomic():
                    record_payment(invoice, self.cashier, tender(f"FIRST-{invoice.pk}", "7.00"))
                    future = pool.submit(worker, lambda: self.receive(invoice.pk, tender(f"SECOND-{invoice.pk}", "6.00")), witness)
                    self.assertTrue(about_to_lock.wait(timeout=15), "Challenger did not reach the owner lock")
                    if rollback_first:
                        transaction.set_rollback(True)
                result, _ = future.result(timeout=40)
                connection.close()
                self.assertEqual(result, "ok" if rollback_first else "conflict")
                self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)
                self.assertEqual(invoice.balance, Decimal("4.00") if rollback_first else Decimal("3.00"))
