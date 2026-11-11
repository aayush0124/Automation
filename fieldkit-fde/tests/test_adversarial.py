"""Independent regression cases discovered by cross-module adversarial review."""

import copy
import re
import unittest

from fieldkit.projects import consentline, dockyard, ledgerguard


class IdentityReconciliationRegressions(unittest.TestCase):
    def test_distinct_normalized_external_ids_are_not_silently_collapsed(self):
        result = dockyard.run({
            "csv": "Name,Email,Customer ID\nMira,mira@example.test,CaseSensitive-ID\nMira,mira@example.test,casesensitive-id\n",
        })
        self.assertEqual(result["metrics"]["clean_customers"], 0)
        self.assertEqual(result["metrics"]["quarantined_rows"], 2)


class FinancialPrecisionRegressions(unittest.TestCase):
    def test_subcent_values_cannot_be_silently_rounded_or_underflowed(self):
        for amount in [
            "0.010000000000000000000000000000000001",
            "999999999.9999999999999999999999999",
            "1e-999999999",
        ]:
            with self.subTest(amount=amount):
                payload = copy.deepcopy(ledgerguard.SAMPLE)
                payload["purchase_orders"][0]["lines"][0]["unit_price"] = amount
                with self.assertRaises(ValueError):
                    ledgerguard.run(payload)


class PrivacyPatternRegressions(unittest.TestCase):
    def test_adjacent_phone_numbers_do_not_escape_minimization(self):
        for text in [
            "Call 9876543210 9123456789",
            "Call (987) 654-3210 (912) 345-6789",
        ]:
            with self.subTest(text=text):
                result = consentline.run({
                    "text": text,
                    "purpose": "support_summary",
                    "consent": {
                        "granted": True,
                        "purposes": ["support_summary"],
                        "data_classes": [],
                    },
                    "keep_classes": [],
                    "mode": "redact",
                })
                if result["egress"]["decision"] == "allow":
                    retained_digits = re.sub(r"\D", "", result["egress"]["text"])
                    self.assertNotIn("9876543210", retained_digits)
                    self.assertNotIn("9123456789", retained_digits)
                else:
                    self.assertIsNone(result["egress"]["text"])


if __name__ == "__main__":
    unittest.main()
