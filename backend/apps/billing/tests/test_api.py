from decimal import Decimal

from django.contrib.auth.models import Permission
from rest_framework.test import APITestCase

from apps.core.models import AuditEvent

from ..models import Invoice, InvoiceItem, Payment
from ..services import close_folio, open_folio, post_order, record_payment
from .fixtures import admitted, meal, staff, tender


class BillingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.office = staff("Accountant")
        cls.desk = staff("Receptionist")
        cls.kitchen = staff("Restaurant Staff")
        cls.stay = admitted("25.05")
        cls.folio = open_folio(cls.stay, cls.desk)
        cls.dining = post_order(meal([("Synthetic breakfast", 1, "25.00")]), cls.kitchen)

    def get(self, path, params=None):
        return self.client.get(f"/api/v1/{path}/", params, secure=True)

    def post(self, path, data):
        return self.client.post(f"/api/v1/{path}/", data, format="json", secure=True)

    def test_nested_and_register_pagination_detail_and_printable_receipt(self):
        self.client.force_authenticate(self.office)
        url = f"invoices/{self.folio.pk}"
        charge = {"description": "Synthetic laundry", "quantity": 2, "unit_price": "25.05", "reference": "TEST-C"}
        self.assertEqual(self.post(f"{url}/charges", charge).status_code, 201)
        self.assertEqual(self.post(f"{url}/charges", charge).status_code, 200)
        receipts = []
        for ref in ("S1", "S2"):
            data = tender(ref, "10.10", "card")
            new = self.post(f"{url}/payments", data)
            self.assertEqual(new.status_code, 201)
            receipt = new.json()
            self.assertEqual((receipt["amount"], receipt["received_by"], receipt["invoice"]),
                             ("10.10", self.office.pk, self.folio.pk))
            self.assertTrue(receipt["receipt_number"].isprintable())
            self.assertEqual(self.get(f"payments/{receipt['id']}").json(), receipt)
            repeat = self.post(f"{url}/payments", data)
            self.assertEqual(repeat.status_code, 200)
            self.assertEqual(repeat.json(), receipt)
            receipts.append(receipt)
        self.assertNotEqual(receipts[0]["receipt_number"], receipts[1]["receipt_number"])
        detail = self.get(url).json()
        self.assertEqual([detail[k] for k in ("total", "paid", "balance")], ["100.20", "20.20", "80.00"])
        self.assertEqual(len(detail["items"]), 2)
        self.assertCountEqual(detail["payments"], receipts)
        self.assertTrue(all(line["created_at"] and line["line_total"] == "50.10" for line in detail["items"]))
        self.assertFalse({"guest", "guest_name", "email", "phone"} & detail.keys())
        for stem in ("payments", f"{url}/payments"):
            with self.subTest(stem=stem):
                first = self.get(stem, {"page_size": 1}).json()
                second = self.get(stem, {"page_size": 1, "page": 2}).json()
                self.assertEqual(first["count"], 2)
                self.assertTrue(first["next"] and second["previous"])
                self.assertIsNone(second["next"])
                self.assertCountEqual(first["results"] + second["results"], receipts)

    def test_filters_status_reservation_and_ownership_stay_server_side(self):
        self.client.force_authenticate(self.office)
        settled, _ = record_payment(self.folio, self.office, tender("FILTER", "50.10"))
        close_folio(self.stay, self.desk)
        for filters, expected in [({"reservation": self.stay.pk}, [self.folio.pk]),
                                  ({"status": "closed"}, [self.folio.pk]), ({"status": "open"}, [self.dining.pk]),
                                  ({"reservation": self.stay.pk, "status": "open"}, [])]:
            with self.subTest(filters=filters):
                page = self.get("invoices", filters).json()
                self.assertEqual(page["count"], len(expected))
                self.assertEqual([r["id"] for r in page["results"]], expected)
        result = self.get("payments", {"reservation": self.stay.pk, "method": "cash", "status": "closed"}).json()
        self.assertEqual([r["id"] for r in result["results"]], [settled.pk])
        self.assertEqual(self.get("payments", {"invoice": self.dining.pk}).json()["count"], 0)
        for param in ({"reservation": "not-a-pk"}, {"status": "cancelled"}):
            self.assertEqual(self.get("invoices", param).status_code, 400)

    def test_reception_reads_only_reservation_folios_and_their_receipts(self):
        folio_payment, _ = record_payment(self.folio, self.office, tender("ROOM"))
        hidden, _ = record_payment(self.dining, self.office, tender("DINING"))
        unrelated = open_folio(admitted("30.00"), self.desk)
        for authorized in (self.office, staff("Hotel Manager")):
            self.client.force_authenticate(authorized)
            register = self.get("invoices").json()
            self.assertCountEqual([r["id"] for r in register["results"]], [self.folio.pk, unrelated.pk, self.dining.pk])
        self.client.force_authenticate(self.desk)
        for params in ({}, {"page_size": 100}, {"status": "open"}, {"search": str(unrelated.pk)}):
            with self.subTest(params=params):
                broad = self.get("invoices", params).json()
                self.assertEqual(broad, {"count": 0, "results": [], "next": None, "previous": None})
        page = self.get("invoices", {"reservation": self.stay.pk, "page_size": 1}).json()
        self.assertEqual(page["count"], 1)
        self.assertEqual([r["id"] for r in page["results"]], [self.folio.pk])
        self.assertEqual(self.get(f"invoices/{self.folio.pk}").json()["reservation"], self.stay.pk)
        self.assertEqual(self.get(f"invoices/{self.folio.pk}/payments").json()["results"][0]["id"], folio_payment.pk)
        self.assertEqual(self.get(f"payments/{folio_payment.pk}").json()["receipt_number"], folio_payment.receipt_number)
        for path in (f"invoices/{self.dining.pk}", f"invoices/{self.dining.pk}/payments", f"payments/{hidden.pk}"):
            self.assertEqual(self.get(path).status_code, 404)
        self.assertEqual(self.get("payments").status_code, 403)  # not even register counts
        for invoice in (self.folio, self.dining):
            for operation in ("charges", "payments"):
                self.assertEqual(self.post(f"invoices/{invoice.pk}/{operation}", {}).status_code, 403)
        self.assertEqual(Payment.objects.count(), 2)

    def test_stray_manage_grant_does_not_promote_reception_to_finance_role(self):
        self.desk.user_permissions.add(Permission.objects.get(codename="billing_manage", content_type__app_label="core"))
        self.client.force_authenticate(self.desk)
        self.assertEqual(self.get("invoices").json()["count"], 0)
        self.assertEqual(self.get("invoices", {"reservation": self.stay.pk}).json()["count"], 1)
        self.assertEqual(self.get("payments").status_code, 403)
        self.assertEqual(self.post(f"invoices/{self.folio.pk}/payments", tender("DENIED")).status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_no_register_detail_or_posting_for_unauthenticated_or_restaurant(self):
        for user in (None, self.kitchen):
            self.client.force_authenticate(user)
            for path in ("payments", "invoices", f"invoices/{self.folio.pk}", f"invoices/{self.folio.pk}/payments"):
                self.assertEqual(self.get(path).status_code, 403)
            self.assertEqual(self.post(f"invoices/{self.folio.pk}/payments", tender("DENIED")).status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_invalid_tenders_and_client_computed_fields_never_record_a_receipt(self):
        self.client.force_authenticate(self.office)
        url = f"invoices/{self.folio.pk}/payments"
        data = tender("INPUT", "1.00")
        cases = [{"amount": value} for value in (0, "-0.01", "NaN", "Infinity", "1.001", "1.000", 1.25, True,
                                                  "10000000000.00", "not money")]
        cases.extend([{"reference": 123}, {"reference": "  "}, {"method": "promise"}, {"receipt_number": "FAKE"},
                      {"received_by": self.desk.pk}, {"paid": "0.00"}, {"invoice": self.dining.pk}])
        for update in cases:
            with self.subTest(update=update):
                self.assertEqual(self.post(url, {**data, **update}).status_code, 400)
        for missing in ("method", "amount", "reference"):
            self.assertEqual(self.post(url, {k: v for k, v in data.items() if k != missing}).status_code, 400)
        self.assertEqual(self.post(url, {**data, "amount": "50.11"}).status_code, 409)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(verb="billing.payment.record").exists())
        self.assertEqual(self.folio.balance, Decimal("50.10"))

    def test_extras_reject_fractional_counts_floats_and_forged_source(self):
        self.client.force_authenticate(self.office)
        url = f"invoices/{self.folio.pk}/charges"
        charge = {"quantity": 2, "description": "Test service", "unit_price": "2.15", "reference": "TEST-VALID"}
        before = InvoiceItem.objects.count()
        for change in ({"unit_price": 2.15}, {"unit_price": "0.001"}, {"quantity": True}, {"quantity": 1.5},
                       {"quantity": "0.1"}, {"source_key": "room:1"}, {"reference": ""}, {"description": "  "},
                       {"status": "paid"}, {"quantity": 2147483648}):
            with self.subTest(change=change):
                self.assertEqual(self.post(url, {**charge, **change}).status_code, 400)
        self.assertEqual(InvoiceItem.objects.count(), before)

    def test_aggregate_strings_can_exceed_a_single_numeric_12_2_input(self):
        self.client.force_authenticate(self.office)
        url = f"invoices/{self.folio.pk}"
        data = {"description": "Synthetic boundary case", "quantity": 2147483647, "unit_price": "9999999999.99",
                "reference": "TEST-LARGE"}
        line = self.post(f"{url}/charges", data)
        self.assertEqual(line.status_code, 201)
        expected = data["quantity"] * Decimal(data["unit_price"])
        self.assertEqual(line.json()["line_total"], f"{expected:.2f}")
        invoice = self.get(url).json()
        self.assertEqual(invoice["balance"], f"{expected + Decimal('50.10'):.2f}")
        self.assertEqual(invoice["total"], invoice["balance"])

    def test_reusing_global_evidence_conflicts_without_returning_another_receipt(self):
        self.client.force_authenticate(self.office)
        existing = tender("STABLE", "10.05", "bank")
        first = self.post(f"invoices/{self.dining.pk}/payments", existing).json()
        for invoice, update in ((self.folio, {}), (self.dining, {"amount": "10.00"}), (self.dining, {"method": "card"})):
            response = self.post(f"invoices/{invoice.pk}/payments", {**existing, **update})
            self.assertEqual(response.status_code, 409)
            self.assertFalse({"invoice", "amount", "reference", "receipt_number", "received_by"} & response.json().keys())
            self.assertNotIn(first["receipt_number"], response.content.decode())
        self.assertEqual(Payment.objects.count(), 1)

    def test_no_api_create_header_edit_postings_or_delete_history(self):
        self.client.force_authenticate(self.office)
        receipt, _ = record_payment(self.folio, self.office, tender("PRESERVE"))
        self.assertIn(self.post("invoices", {"reservation": self.stay.pk}).status_code, (403, 405))
        self.assertIn(self.post("payments", tender("FORGED")).status_code, (403, 405))
        for url in (f"/api/v1/invoices/{self.folio.pk}/", f"/api/v1/payments/{receipt.pk}/"):
            self.assertIn(self.client.patch(url, {"amount": "9.00"}, format="json", secure=True).status_code, (403, 405))
            self.assertIn(self.client.delete(url, secure=True).status_code, (403, 405))
        self.assertEqual(Payment.objects.get().amount, Decimal("1.00"))
        self.assertEqual(Invoice.objects.count(), 2)
