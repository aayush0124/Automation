import copy
import unittest

from fieldkit.projects.dockyard import SAMPLE, run


class DockyardTests(unittest.TestCase):
    def test_sample_counts_and_conservation(self):
        result = run(copy.deepcopy(SAMPLE))
        self.assertEqual(result["metrics"]["clean_customers"], 2)
        self.assertEqual(result["metrics"]["quarantined_rows"], 3)
        self.assertEqual(result["metrics"]["duplicates_collapsed"], 1)
        self.assertEqual(result["metrics"]["input_rows"], result["metrics"]["accepted_source_rows"] + result["metrics"]["quarantined_rows"])

    def test_normalization_and_all_duplicate_lineage(self):
        records = run(SAMPLE)["records"]
        mira = next(r for r in records if r["email"] == "mira@example.test")
        self.assertEqual(mira["name"], "Mira Shah")
        self.assertEqual(mira["country"], "IN")
        self.assertEqual(mira["source_rows"], [2, 3])
        self.assertEqual(mira["lineage"]["email"][0]["raw"], "MIRA@example.test")

    def test_conflicting_identity_quarantines_every_row(self):
        out = run({"csv": "id,name,email\nA,Joe,j@example.test\nB,Joe,j@example.test\n"})
        self.assertEqual(out["records"], [])
        self.assertEqual(len(out["quarantine"]), 2)
        self.assertIn("conflicting_values:external_id", out["quarantine"][0]["reasons"])

    def test_same_external_id_different_emails_quarantines_both(self):
        out = run({"csv": "id,name,email\nA,Joe,j@example.test\nA,Joe,x@example.test\n"})
        self.assertEqual(out["metrics"]["quarantined_rows"], 2)
        self.assertEqual(out["records"], [])

    def test_custom_mapping_quoted_csv_and_unknown_column(self):
        out = run({"csv": 'Person,Contact,Notes\n"Doe, Jane",jane@example.test,"hello, world"\n', "mapping": {"Person": "name", "Contact": "email"}})
        self.assertEqual(out["records"][0]["name"], "Doe, Jane")
        self.assertTrue(any("Notes" in w for w in out["warnings"]))

    def test_formula_and_ragged_rows_are_quarantined(self):
        out = run({"csv": "name,email\n=HYPERLINK(x),j@example.test\nJoe,j@example.test,extra\n"})
        self.assertEqual(out["metrics"]["quarantined_rows"], 2)
        self.assertEqual(out["records"], [])

    def test_ambiguous_and_duplicate_headers_rejected(self):
        for text in ("name,email,E-mail\nJoe,a@b.test,a@b.test", "name,email,EMAIL\nJoe,a@b.test,a@b.test"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                run({"csv": text})

    def test_invalid_mapping_missing_header_and_nonobject_rejected(self):
        for payload in ([], {"csv": "name,email\n", "mapping": {"x": "name"}}, {"csv": "name,email\n", "mapping": {"name": []}}, {"csv": "name,company\nJoe,Acme"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run(payload)

    def test_blank_rows_do_not_inflate_quality(self):
        out = run({"csv": "name,email\n\n,\nJoe,j@example.test\n"})
        self.assertEqual(out["metrics"]["input_rows"], 1)
        self.assertEqual(out["metrics"]["accepted_row_percent"], 100.0)

    def test_malformed_quotes_rejected(self):
        with self.assertRaises(ValueError):
            run({"csv": 'name,email\n"Joe,j@example.test'})


if __name__ == "__main__":
    unittest.main()
