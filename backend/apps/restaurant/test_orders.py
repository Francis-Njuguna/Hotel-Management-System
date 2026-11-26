"""Synthetic tickets exercising the actual restaurant API and ledger boundary."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.core.api import Conflict
from apps.core.models import AuditEvent
from apps.lodging.models import Guest, Reservation, Room, RoomClaim

from .models import MenuItem, Order, OrderItem
from .services import assert_no_open_orders


class OrderTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        staff = Group.objects.get(name="Restaurant Staff")
        cls.cook = get_user_model().objects.create_user("synthetic-kitchen-a")
        cls.peer = get_user_model().objects.create_user("synthetic-kitchen-b")
        cls.cook.groups.add(staff)
        cls.peer.groups.add(staff)
        cls.other = get_user_model().objects.create_user("synthetic-other-department")
        cls.other.groups.add(Group.objects.get(name="Receptionist"))
        cls.meal = MenuItem.objects.create(name="Synthetic meal", category="Kitchen", price=Decimal("12.35"))

    def setUp(self):
        self.client.force_authenticate(self.cook)

    def place(self, **values):
        return self.client.post("/api/v1/orders/", {"items": [{"menu_item": self.meal.pk, "quantity": 3}], **values},
                                format="json", secure=True)

    def change(self, pk, state, **extra):
        return self.client.post(f"/api/v1/orders/{pk}/transition/", {"status": state, **extra}, format="json", secure=True)

    def check(self, response, code):
        self.assertEqual(response.status_code, code, response.content)
        return response.json()

    def new_stay(self, number="RS-01"):
        now = timezone.now()
        arrive = timezone.localdate()
        guest = Guest.objects.create(full_name="Synthetic room-service guest")
        stay = Reservation.objects.create(guest=guest, arrival=arrive, departure=arrive + timedelta(days=1),
                                          status="checked_in", checked_in_at=now)
        room = Room.objects.create(number=number, category="Single", capacity=1, nightly_rate=Decimal("10.00"))
        RoomClaim.objects.create(reservation=stay, room=room, start=stay.arrival, end=stay.departure,
                                 nightly_rate=room.nightly_rate, blocking=True)
        # Admitted-stay fixture; isolate food postings from accommodation charges.
        invoice = Invoice.objects.create(reservation=stay)
        return stay, room, invoice

    def test_withdrawal_after_selection_rejects_whole_ticket(self):
        side = MenuItem.objects.create(name="Synthetic side", category="Kitchen", price=Decimal("2.15"))
        chosen = [{"menu_item": self.meal.pk, "quantity": 1}, {"menu_item": side.pk, "quantity": 2}]
        self.check(self.client.patch(f"/api/v1/menu-items/{side.pk}/", {"available": False}, format="json", secure=True), 200)
        self.check(self.place(items=chosen), 409)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(verb="order.created").exists())
        self.check(self.place(items=chosen[:1]), 201)

    def test_kitchen_cannot_inject_price_total_guest_state_or_invalid_quantity(self):
        for forged in ({"status": "served"}, {"total": "0.00"}, {"guest": 1},
                       {"items": [{"menu_item": self.meal.pk, "quantity": 1, "unit_price": "0.01"}]},
                       {"items": [{"menu_item": self.meal.pk, "quantity": 0}]},
                       {"items": [{"menu_item": self.meal.pk, "quantity": "1.5"}]}, {"items": []}):
            with self.subTest(forged=forged):
                self.check(self.place(**forged), 400)
        self.assertFalse(Order.objects.exists())
        order = self.check(self.place(), 201)
        self.check(self.client.patch(f"/api/v1/orders/{order['id']}/", {"status": "served"}, format="json", secure=True), 400)
        self.assertEqual(Order.objects.get().status, "pending")

    def test_assignment_uses_locked_active_restaurant_membership_and_early_states(self):
        self.check(self.place(assignee=self.other.pk), 400)
        pk = self.check(self.place(), 201)["id"]
        url = f"/api/v1/orders/{pk}/"
        assigned = self.check(self.client.patch(url, {"assignee": self.peer.pk}, format="json", secure=True), 200)
        self.assertEqual((assigned["status"], assigned["assignee"]), ("pending", self.peer.pk))
        self.assertIsNone(self.check(self.change(pk, "confirmed", assignee=None), 200)["assignee"])
        self.peer.is_active = False
        self.peer.save(update_fields=["is_active"])
        self.check(self.change(pk, "preparing", assignee=self.peer.pk), 400)
        self.assertEqual((Order.objects.get().status, Order.objects.get().assignee_id), ("confirmed", None))
        self.check(self.change(pk, "confirmed", assignee=self.cook.pk), 200)
        self.check(self.change(pk, "preparing"), 200)
        self.check(self.client.patch(url, {"assignee": None}, format="json", secure=True), 409)
        self.assertEqual(Order.objects.get().assignee_id, self.cook.pk)

    def test_cancel_from_each_pre_served_state_without_a_charge(self):
        progression = ("confirmed", "preparing", "ready")
        for step in range(4):
            with self.subTest(prior=step):
                pk = self.check(self.place(), 201)["id"]
                self.check(self.change(pk, "ready"), 409)  # No skipped stages.
                for state in progression[:step]:
                    self.check(self.change(pk, state), 200)
                self.assertEqual(self.check(self.change(pk, "cancelled"), 200)["status"], "cancelled")
                self.check(self.change(pk, "confirmed"), 409)
                self.check(self.change(pk, "served"), 409)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(InvoiceItem.objects.exists())

    def test_dine_in_serves_snapshot_once_with_candidate_before_order_lock(self):
        ticket = self.check(self.place(), 201)
        pk = ticket["id"]
        self.assertIsNone(ticket["guest"])
        self.assertEqual(ticket["total"], "37.05")
        self.check(self.client.patch(f"/api/v1/menu-items/{self.meal.pk}/", {"price": "20.00"}, format="json", secure=True), 200)
        for state in ("confirmed", "preparing", "ready"):
            self.check(self.change(pk, state), 200)
        self.assertFalse(Invoice.objects.exists())
        with CaptureQueriesContext(connection) as sql:
            served = self.check(self.change(pk, "served"), 200)
        self.assertEqual((served["status"], served["total"], served["items"][0]["unit_price"]), ("served", "37.05", "12.35"))
        # A status UPDATE also locks the order, even without a SELECT FOR UPDATE.
        statements = [q["sql"].upper() for q in sql]
        invoice_insert = next(i for i, q in enumerate(statements) if q.startswith('INSERT INTO "BILLING_INVOICE"'))
        order_lock = next(i for i, q in enumerate(statements) if q.startswith('UPDATE "RESTAURANT_ORDER"') or
                          ('FROM "RESTAURANT_ORDER"' in q and (" FOR UPDATE" in q or " FOR NO KEY UPDATE" in q)))
        self.assertLess(invoice_insert, order_lock)
        self.check(self.change(pk, "served"), 200)
        self.check(self.change(pk, "cancelled"), 409)
        invoice = Invoice.objects.get()
        self.assertIsNone(invoice.reservation_id)
        line = InvoiceItem.objects.get(invoice=invoice)
        self.assertEqual((line.unit_price, line.quantity), (Decimal("12.35"), 3))
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(AuditEvent.objects.filter(verb="order.served").count(), 1)

    def test_room_service_lookup_binding_checkout_guard_and_posting_rollback(self):
        stay, room, invoice = self.new_stay()
        closed, former_room, old_folio = self.new_stay("RS-02")
        closed.status, closed.checked_out_at = "checked_out", timezone.now()
        closed.save(update_fields=["status", "checked_out_at"])
        old_folio.closed_at = timezone.now()
        old_folio.save(update_fields=["closed_at"])
        stays = self.check(self.client.get("/api/v1/orders/stays/?page_size=1", secure=True), 200)
        self.assertEqual(stays["count"], 1)
        self.assertEqual(stays["results"], [{"id": stay.pk, "rooms": [{"id": room.pk, "number": room.number}]}])
        self.check(self.place(room=room.pk), 400)
        self.check(self.place(reservation=stay.pk, room=former_room.pk), 400)
        self.check(self.place(reservation=closed.pk, room=former_room.pk), 409)
        ticket = self.check(self.place(reservation=stay.pk), 201)  # resolve the only booked room
        self.assertEqual((ticket["room"], ticket["guest"]), (room.pk, stay.guest_id))
        with self.assertRaises(Conflict), transaction.atomic():
            assert_no_open_orders(stay)
        pk = ticket["id"]
        for state in ("confirmed", "preparing", "ready"):
            self.check(self.change(pk, state), 200)
        with patch("apps.billing.services.post_order", side_effect=Conflict("Synthetic posting refusal.")):
            self.check(self.change(pk, "served"), 409)
        self.assertEqual(Order.objects.get(pk=pk).status, "ready")
        self.assertFalse(InvoiceItem.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(verb="order.served").exists())
        self.check(self.change(pk, "served"), 200)
        with transaction.atomic():
            assert_no_open_orders(stay)
        self.assertEqual(InvoiceItem.objects.get().invoice_id, invoice.pk)
        self.assertFalse(Payment.objects.exists())
        self.client.force_authenticate(self.other)
        self.check(self.client.get("/api/v1/orders/stays/", secure=True), 403)
