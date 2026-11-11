import copy
import json
import unittest

from fieldkit.projects.consentline import SAMPLE, detect, run


class ConsentLineTests(unittest.TestCase):
    def payload(self, **updates):
        value = copy.deepcopy(SAMPLE)
        value.update(updates)
        return value

    def test_sample_minimizes_every_entity_and_keeps_no_plaintext_audit(self):
        result = run(self.payload())
        self.assertEqual(result["metrics"]["detected_entities"], 4)
        self.assertEqual(result["egress"]["decision"], "allow")
        for raw in ("mira@example.test", "+91 98765 43210", "ABCDE1234F"):
            self.assertNotIn(raw, json.dumps(result))
        self.assertNotIn(SAMPLE["pseudonym_key"], json.dumps(result))

    def test_repeated_identifiers_share_pseudonyms(self):
        result = run(self.payload(text="MIRA@example.test then mira@example.test"))
        self.assertEqual(result["records"][0]["replacement"], result["records"][1]["replacement"])

    def test_keys_and_purposes_partition_pseudonyms(self):
        first = run(self.payload())
        second = run(self.payload(pseudonym_key="different-public-demo-key"))
        third_payload = self.payload(purpose="aggregate_analytics")
        third_payload["consent"]["purposes"] = ["aggregate_analytics"]
        third = run(third_payload)
        self.assertNotEqual(first["records"][0]["replacement"], second["records"][0]["replacement"])
        self.assertNotEqual(first["records"][0]["replacement"], third["records"][0]["replacement"])

    def test_contact_reply_retains_only_explicit_authorized_class(self):
        result = run(self.payload(
            purpose="contact_reply", keep_classes=["email"],
            consent={"granted": True, "purposes": ["contact_reply"], "data_classes": ["email"]},
        ))
        self.assertEqual(result["egress"]["decision"], "allow")
        self.assertIn("mira@example.test", result["egress"]["text"])
        self.assertNotIn("98765", result["egress"]["text"])
        self.assertEqual(result["metrics"]["retained_entities"], 2)
        self.assertNotIn("mira@example.test", json.dumps(result["records"]))

    def test_forbidden_raw_class_denies_even_when_consent_claims_permission(self):
        result = run(self.payload(keep_classes=["email"], consent={
            "granted": True, "purposes": ["support_summary"], "data_classes": ["email"],
        }))
        self.assertIn("RAW_CLASS_FORBIDDEN_FOR_PURPOSE", result["egress"]["reasons"])
        self.assertIsNone(result["egress"]["text"])

    def test_missing_consent_for_raw_class_denies(self):
        result = run(self.payload(purpose="contact_reply", keep_classes=["email"], consent={
            "granted": True, "purposes": ["contact_reply"], "data_classes": [],
        }))
        self.assertIn("RAW_CLASS_NOT_CONSENTED", result["egress"]["reasons"])
        self.assertEqual(result["metrics"]["retained_entities"], 0)

    def test_revoked_or_wrong_purpose_consent_denies(self):
        for consent, reason in [
            ({"granted": False, "purposes": ["support_summary"], "data_classes": []}, "CONSENT_NOT_GRANTED"),
            ({"granted": True, "purposes": ["contact_reply"], "data_classes": []}, "PURPOSE_NOT_CONSENTED"),
        ]:
            with self.subTest(reason=reason):
                result = run(self.payload(consent=consent))
                self.assertIn(reason, result["egress"]["reasons"])
                self.assertIsNone(result["egress"]["text"])

    def test_unknown_purpose_fails_closed(self):
        result = run(self.payload(purpose="unregistered", consent={
            "granted": True, "purposes": ["unregistered"], "data_classes": [],
        }))
        self.assertIn("UNKNOWN_PURPOSE", result["egress"]["reasons"])
        self.assertEqual(result["egress"]["decision"], "deny")

    def test_offsets_are_original_unicode_character_offsets(self):
        text = "😀 नमस्ते mira@example.test; PAN ABCDE1234F."
        matches = detect(text)
        self.assertEqual([text[m["start"]:m["end"]] for m in matches], ["mira@example.test", "ABCDE1234F"])
        self.assertEqual(matches[0]["start"], text.index("mira"))

    def test_email_overlap_takes_precedence_over_pan_substring(self):
        matches = detect("ABCDE1234F@example.test")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["data_class"], "email")

    def test_phone_normalization_and_digit_bounds(self):
        result = run(self.payload(text="+1 202-555-0100 and 12025550100"))
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["replacement"], result["records"][1]["replacement"])
        self.assertEqual(detect("Short 123456789"), [])
        ambiguous = run(self.payload(text="Too long 12345678901234567890"))
        self.assertEqual(ambiguous["egress"]["decision"], "deny")
        self.assertIn("AMBIGUOUS_PHONE_SPAN", ambiguous["egress"]["reasons"])

    def test_redact_mode_needs_no_key(self):
        payload = self.payload(mode="redact")
        del payload["pseudonym_key"]
        result = run(payload)
        self.assertIn("[REDACTED_EMAIL]", result["egress"]["text"])
        self.assertNotIn("mira@example.test", result["egress"]["text"])

    def test_no_match_does_not_claim_safe_text(self):
        result = run(self.payload(text="Jane at Maple Cottage"))
        self.assertEqual(result["metrics"]["detected_entities"], 0)
        self.assertTrue(any("not proof" in warning for warning in result["warnings"]))

    def test_invalid_shapes_are_value_errors(self):
        bad = [None, [], self.payload(text=""), self.payload(text="x" * 100001),
               self.payload(mode="raw"), self.payload(mode=[]),
               self.payload(pseudonym_key="short"), self.payload(keep_classes=["email", "email"]),
               self.payload(keep_classes=["address"]), self.payload(consent={"granted": "true"})]
        for payload in bad:
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(ValueError):
                    run(payload)

    def test_input_is_not_mutated(self):
        payload = self.payload()
        before = copy.deepcopy(payload)
        run(payload)
        self.assertEqual(payload, before)


if __name__ == "__main__":
    unittest.main()
