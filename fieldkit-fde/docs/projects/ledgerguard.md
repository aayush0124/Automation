# LedgerGuard — evidence-driven invoice reconciliation

## Customer discovery brief

A procurement team receives invoices before all goods arrive, pays multiple partial invoices against one purchase order, and works with more than one currency. Comparing each invoice to the original order independently can approve the same received units twice. The first deployment should explain every hold and leave payment authority with a human.

**Discovery questions:** Are partial deliveries billable? What price variance is allowed? Do freight and tax have separate lines? How are credit notes and returns represented? Which system owns payment status? Can an invoice number repeat across suppliers?

## Working implementation

`fieldkit/projects/ledgerguard.py` matches invoice lines against purchase-order prices and cumulative goods receipts. Monetary values are accepted as decimal strings or integers, converted exactly to integer cents, and never accumulated across currencies. Incoming floats and amounts with more than two fractional digits are rejected.

The engine checks supplier, currency, order and SKU identity, price ceilings, duplicate invoice IDs and available unbilled receipt quantities. Prior-paid lines reserve quantities before the new batch. Each newly matched invoice reserves its units only after **all** lines pass; a held multi-line invoice cannot consume capacity needed by a later valid invoice. Input order defines reservation priority.

| Failure | Result | Evidence |
|---|---|---|
| Invoice exceeds unbilled received quantity | Hold | Ordered, received, previously allocated and available quantities |
| Price exceeds purchase order | Hold | Invoice and order unit prices in cents |
| Currency or vendor differs | Hold | Reason code and invoice identity |
| Duplicate invoice ID in batch or prior payments | Hold | Duplicate reason; all batch copies held |
| Duplicate goods-receipt ID | Input rejected | Prevents receipt double counting |
| One bad line on otherwise valid invoice | Entire invoice held | No partial reservation |

## Minimal input

```json
{
  "purchase_orders": [{"id": "PO-1", "vendor": "Harbour Parts", "currency": "INR", "lines": [
    {"sku": "FILTER-A", "quantity": 10, "unit_price": "125.50"}
  ]}],
  "receipts": [{"id": "GR-1", "po_id": "PO-1", "sku": "FILTER-A", "quantity": 6}],
  "prior_paid": [],
  "invoices": [{"id": "INV-1", "po_id": "PO-1", "vendor": "Harbour Parts", "currency": "INR", "lines": [
    {"sku": "FILTER-A", "quantity": 4, "unit_price": "125.50"}
  ]}]
}
```

Bundled companies, invoices, receipts and amounts are synthetic. To represent a previous payment, add a `prior_paid` object with `invoice_id`, `po_id`, `sku`, integer `quantity` and `currency`.

## 90-second interview demo

1. Run the sample. One invoice matches for human review; three are held. The first reserves four of six received filters. The second asks for three when only two remain.
2. Change the second invoice quantity from three to two and run again. It now matches. Show that results follow the supplied records, not hardcoded outcomes.
3. Add a second, overpriced line to the first invoice. It is held atomically; later invoices can still use the filter capacity. Show the test that prevents partial reservations on failed invoices.

## Acceptance evidence

```bash
python -m unittest discover -s tests -p test_ledgerguard.py -v
```

Twelve tests cover sample outcomes, exact currency-separated totals, aggregate receipt consumption, duplicate invoices and receipts, prior payments, atomic reservations, order caps despite over-receipts, invalid money and quantities, and supplier/order/SKU mismatches. The sample's matched total of 50,200 INR cents is computed, not a savings claim.

## Deployment and handoff

This is a stateless reconciliation preview; `ready_for_review` does not mean paid. A real integration needs signed ERP/webhook inputs, supplier-scoped invoice identities, persistent transactional reservations, concurrent-processing controls, approval roles, audit history, idempotent payment handoff, retention policy and exception queues. Validate payment history and goods-return semantics with the customer before rollout.

The current model intentionally supports positive whole-unit quantities, nonnegative two-decimal amounts, exact or lower prices, and syntactically three-letter currency codes. It does not implement ISO currency minor-unit rules, tax, FX, discounts, credit notes, returns, payment execution or invoice OCR. Production ingestion must normalize these concepts explicitly; do not treat this demo as accounting or tax advice.

**Commercial hypothesis:** a procurement exception-queue pilot integrated with an existing ERP. Measure manual touches per invoice, exception precision, false holds and reconciliation latency against a labeled customer batch. No measured savings or production deployment is claimed.
