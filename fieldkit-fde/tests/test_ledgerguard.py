import copy
import unittest

from fieldkit.projects.ledgerguard import SAMPLE, run


class LedgerGuardTests(unittest.TestCase):
    def setUp(self):
        self.payload = copy.deepcopy(SAMPLE)

    def test_sample_exact_amount_and_independent_hold_reasons(self):
        out = run(self.payload)
        self.assertEqual(out["metrics"], {"invoices": 4, "matched": 1, "held": 3})
        self.assertEqual(out["matched_amount_cents_by_currency"], {"INR": 50200})
        self.assertIn("price_above_order:VALVE-B", out["records"][2]["reasons"])
        self.assertIn("currency_mismatch", out["records"][3]["reasons"])

    def test_aggregate_receipts_cannot_be_billed_twice(self):
        out = run(self.payload)
        self.assertEqual(out["records"][1]["evidence"][0]["available_quantity"], 2)
        self.assertIn("quantity_exceeds_unbilled_receipts:FILTER-A", out["records"][1]["reasons"])

    def test_duplicate_invoice_ids_hold_all_copies(self):
        self.payload["invoices"] = [self.payload["invoices"][0], copy.deepcopy(self.payload["invoices"][0])]
        out = run(self.payload)
        self.assertEqual(out["metrics"]["held"], 2)
        self.assertTrue(all("duplicate_invoice_id" in r["reasons"] for r in out["records"]))

    def test_prior_paid_quantity_reduces_availability(self):
        self.payload["prior_paid"] = [{"invoice_id": "OLD", "po_id": "PO-100", "sku": "FILTER-A", "quantity": 3, "currency": "INR"}]
        out = run(self.payload)
        self.assertEqual(out["records"][0]["decision"], "hold")
        self.assertEqual(out["records"][1]["decision"], "ready_for_review")

    def test_previously_paid_invoice_is_duplicate(self):
        self.payload["prior_paid"] = [{"invoice_id": "INV-1", "po_id": "PO-100", "sku": "FILTER-A", "quantity": 1, "currency": "INR"}]
        self.assertIn("duplicate_invoice_id", run(self.payload)["records"][0]["reasons"])

    def test_multi_line_hold_does_not_reserve_valid_line(self):
        bad = copy.deepcopy(self.payload["invoices"][0])
        bad["id"] = "BAD"
        bad["lines"].append({"sku": "VALVE-B", "quantity": 1, "unit_price": "999.00"})
        self.payload["invoices"].insert(0, bad)
        out = run(self.payload)
        self.assertEqual(out["records"][0]["decision"], "hold")
        self.assertEqual(out["records"][1]["decision"], "ready_for_review")
        self.assertEqual(out["records"][1]["evidence"][0]["previously_allocated_quantity"], 0)

    def test_order_quantity_caps_over_receipt(self):
        self.payload["receipts"][0]["quantity"] = 100
        self.payload["invoices"][0]["lines"][0]["quantity"] = 11
        self.assertEqual(run(self.payload)["records"][0]["decision"], "hold")

    def test_duplicate_receipt_rejected(self):
        self.payload["receipts"].append(copy.deepcopy(self.payload["receipts"][0]))
        with self.assertRaises(ValueError):
            run(self.payload)

    def test_invalid_money_never_silently_rounds(self):
        for price in ("1.001", "NaN", "Infinity", -1, 1.25, True):
            payload = copy.deepcopy(SAMPLE)
            payload["invoices"][0]["lines"][0]["unit_price"] = price
            with self.subTest(price=price), self.assertRaises(ValueError):
                run(payload)

    def test_vendor_unknown_order_and_unknown_sku_hold(self):
        for field, value, reason in (("vendor", "Wrong Vendor", "vendor_mismatch"), ("po_id", "MISSING", "unknown_purchase_order")):
            payload = copy.deepcopy(SAMPLE)
            payload["invoices"][0][field] = value
            self.assertIn(reason, run(payload)["records"][0]["reasons"])
        self.payload["invoices"][0]["lines"][0]["sku"] = "MISSING"
        self.assertIn("unknown_order_sku:MISSING", run(self.payload)["records"][0]["reasons"])

    def test_currency_totals_are_not_combined(self):
        usd_po = copy.deepcopy(self.payload["purchase_orders"][0])
        usd_po.update(id="PO-USD", currency="USD")
        self.payload["purchase_orders"].append(usd_po)
        self.payload["receipts"].append({"id": "GR-USD", "po_id": "PO-USD", "sku": "VALVE-B", "quantity": 1})
        self.payload["invoices"][3]["po_id"] = "PO-USD"
        self.assertEqual(run(self.payload)["matched_amount_cents_by_currency"], {"INR": 50200, "USD": 30000})

    def test_fractional_quantity_rejected(self):
        self.payload["invoices"][0]["lines"][0]["quantity"] = 1.5
        with self.assertRaises(ValueError):
            run(self.payload)


if __name__ == "__main__":
    unittest.main()
