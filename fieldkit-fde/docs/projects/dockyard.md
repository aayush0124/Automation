# Dockyard — a customer-data migration workbench

## Customer discovery brief

A customer-success team acquires a second business. Its CRM export uses different headers, inconsistent capitalization, duplicate contacts and conflicting customer IDs. An import that silently chooses the first row can attach a renewal to the wrong person. The first useful deployment is an auditable import preview that operators can understand before writing to the destination CRM.

**Discovery questions:** Which system owns customer identity? Can one email represent multiple accounts? Are missing values equivalent to unknown, or should a merge preserve the old value? Who approves conflict resolution? This demo chooses conservative rules and makes those assumptions visible.

## Working implementation

`fieldkit/projects/dockyard.py` parses CSV with Python's CSV reader; resolves known aliases and explicit header mappings; normalizes whitespace, email case and two-letter country codes; checks row shape and required values; groups by normalized email; then quarantines conflicting groups. It also catches one external ID associated with multiple emails. Exact normalized duplicates collapse into one customer while retaining every source row and every mapped cell's raw value.

| Step | Decision | Evidence |
|---|---|---|
| Schema mapping | Name and email are required; ambiguous mappings fail | Resolved header mapping |
| Validation | Bad email shape, malformed row, or formula-prefixed mapped cell is quarantined | Row number and reason codes |
| Identity reconciliation | Conflicting canonical values or ID/email collisions quarantine every affected row | Field-level lineage for each row |
| Deduplication | Equivalent normalized records collapse | All source rows, raw and normalized cells |

No database or CRM is written. Ignored source columns are named in warnings. A two-letter country format check is not country-code validation; the email check is deliberately simple, not RFC validation. Formula-prefix blocking is conservative protection for a future spreadsheet export, not a general sanitizer.

## Minimal input

```json
{
  "csv": "Full Name,E-mail,Customer ID\nMira Shah,MIRA@example.test,C-1\nMira Shah,mira@example.test,C-1\n",
  "mapping": {"Customer ID": "external_id"}
}
```

All bundled names, businesses and addresses are synthetic. Explicit mappings use **source header → canonical field**; supported fields are `external_id`, `name`, `email`, `company`, `country`.

## 90-second interview demo

1. Run the bundled sample. Six source rows yield two clean customers, three quarantined rows and one collapsed duplicate. Open Mira's lineage to show why uppercase email and surrounding whitespace are safe to normalize.
2. Inspect the two Dev rows. They share one email but disagree on external ID; neither is silently accepted. Fix `C-999` to `C-102` and run again to show a real change in the computed results.
3. Change Ana's external ID to `C-101`. Show that both customers are held even though their emails differ. Explain the conservative identity assumption and how a real customer's ownership rules would alter it.

## Acceptance evidence

```bash
python -m unittest discover -s tests -p test_dockyard.py -v
```

Ten tests cover row-count conservation, quote-aware CSV parsing, duplicate lineage, both identity-conflict directions, malformed records, spreadsheet-formula prefixes, ambiguous schemas, invalid mappings and blank-row handling. The sample's accepted-source-row percentage is computed from input rows; it is not a claimed customer improvement.

## Deployment and handoff

The engine is stateless and standard-library-only. It is suitable for an inspectable portfolio demo. A production migration needs source/destination connectors, trusted tenant boundaries, encrypted storage, retention policy, resumable jobs, operator decisions stored with an audit trail, write previews, idempotent destination upserts and rollback. Add integration fixtures from an authorized customer's actual export format, plus volume tests, before making throughput claims.

**Commercial hypothesis:** sell a fixed-scope CRM migration diagnostic, then implement the approved importer. Measure operator review time, unresolved identity conflicts and post-import correction rate against the customer's baseline. No revenue or efficiency result has been measured for this synthetic demo.
