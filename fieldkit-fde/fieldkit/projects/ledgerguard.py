"""Three-way invoice matching with exact amounts and aggregate receipt allocation."""
from __future__ import annotations

from collections import defaultdict
import re

SPEC = {
    "id": "ledgerguard", "name": "LedgerGuard", "track": "operations",
    "tagline": "Every invoice decision has a receipt trail.",
    "description": "Reconcile invoices against purchase orders and goods receipts with exact money and review holds.",
    "customer": "A procurement team reconciling supplier invoices across currencies",
    "skills": ["financial data integration", "exact arithmetic", "reconciliation", "auditability"],
    "flagship": False,
}
SAMPLE = {
    "purchase_orders": [{"id": "PO-100", "vendor": "Harbour Parts", "currency": "INR", "lines": [
        {"sku": "FILTER-A", "quantity": 10, "unit_price": "125.50"},
        {"sku": "VALVE-B", "quantity": 4, "unit_price": "300.00"}]}],
    "receipts": [{"id": "GR-1", "po_id": "PO-100", "sku": "FILTER-A", "quantity": 6},
                 {"id": "GR-2", "po_id": "PO-100", "sku": "VALVE-B", "quantity": 4}],
    "prior_paid": [],
    "invoices": [
        {"id": "INV-1", "po_id": "PO-100", "vendor": "Harbour Parts", "currency": "INR", "lines": [{"sku": "FILTER-A", "quantity": 4, "unit_price": "125.50"}]},
        {"id": "INV-2", "po_id": "PO-100", "vendor": "Harbour Parts", "currency": "INR", "lines": [{"sku": "FILTER-A", "quantity": 3, "unit_price": "125.50"}]},
        {"id": "INV-3", "po_id": "PO-100", "vendor": "Harbour Parts", "currency": "INR", "lines": [{"sku": "VALVE-B", "quantity": 2, "unit_price": "350.00"}]},
        {"id": "INV-4", "po_id": "PO-100", "vendor": "Harbour Parts", "currency": "USD", "lines": [{"sku": "VALVE-B", "quantity": 1, "unit_price": "300.00"}]},
    ],
}


def _text(obj: dict, field: str) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(field + " must contain 1 to 200 characters.")
    return value.strip()


def _quantity(obj: dict) -> int:
    value = obj.get("quantity")
    if type(value) is not int or not 1 <= value <= 1_000_000:
        raise ValueError("quantity must be an integer from 1 to 1,000,000.")
    return value


def _money(value) -> int:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("unit_price must be a decimal string or an integer, never a float.")
    # Parse decimal digits directly: Decimal arithmetic can silently round a
    # long coefficient or underflow a hostile exponent under the active context.
    raw = str(value)
    if len(raw) > 32 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", raw):
        raise ValueError("unit_price requires plain nonnegative decimal digits with at most two fractional digits; exponents are unsupported.")
    whole, _, fractional = raw.partition(".")
    cents = int(whole) * 100 + int(fractional.ljust(2, "0"))
    if cents > 100_000_000_000:
        raise ValueError("unit_price must not exceed 1,000,000,000.")
    return cents


def _currency(obj: dict) -> str:
    value = _text(obj, "currency")
    if not re.fullmatch("[A-Z]{3}", value):
        raise ValueError("currency must be a three-letter uppercase code.")
    return value


def _lines(obj: dict) -> dict:
    lines = obj.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 500:
        raise ValueError("lines must contain 1 to 500 entries.")
    result = {}
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Each line must be an object.")
        sku = _text(line, "sku")
        if sku in result:
            raise ValueError("Duplicate SKU lines must be consolidated before matching.")
        result[sku] = {"quantity": _quantity(line), "unit_price_cents": _money(line.get("unit_price"))}
    return result


def run(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object.")
    for key in ("purchase_orders", "receipts", "invoices", "prior_paid"):
        items = payload.get(key, [] if key == "prior_paid" else None)
        if not isinstance(items, list) or len(items) > 2000 or any(not isinstance(i, dict) for i in items):
            raise ValueError(key + " must be a list of at most 2,000 objects.")
    orders = {}
    for po in payload["purchase_orders"]:
        pid = _text(po, "id")
        if pid in orders:
            raise ValueError("Purchase order IDs must be unique.")
        orders[pid] = {"vendor": _text(po, "vendor"), "currency": _currency(po), "lines": _lines(po)}
    received, receipt_ids, receipt_refs = defaultdict(int), set(), defaultdict(list)
    for receipt in payload["receipts"]:
        rid, pid, sku = (_text(receipt, k) for k in ("id", "po_id", "sku"))
        if rid in receipt_ids:
            raise ValueError("Receipt IDs must be unique; duplicates would inflate received quantities.")
        if pid not in orders or sku not in orders[pid]["lines"]:
            raise ValueError("A receipt references an unknown purchase order or SKU.")
        receipt_ids.add(rid)
        received[(pid, sku)] += _quantity(receipt)
        receipt_refs[(pid, sku)].append(rid)
    allocated, prior_ids, prior_keys = defaultdict(int), set(), set()
    for line in payload.get("prior_paid", []):
        iid, pid, sku = (_text(line, k) for k in ("invoice_id", "po_id", "sku"))
        if (iid, pid, sku) in prior_keys or pid not in orders or sku not in orders[pid]["lines"]:
            raise ValueError("Prior-paid lines must be unique and reference known order lines.")
        if _currency(line) != orders[pid]["currency"]:
            raise ValueError("A prior-paid line has a currency mismatch.")
        prior_keys.add((iid, pid, sku))
        prior_ids.add(iid)
        allocated[(pid, sku)] += _quantity(line)
    invoices, counts = [], defaultdict(int)
    for invoice in payload["invoices"]:
        normalized = {k: _text(invoice, k) for k in ("id", "po_id", "vendor")}
        normalized.update(currency=_currency(invoice), lines=_lines(invoice))
        invoices.append(normalized)
        counts[normalized["id"]] += 1
    records, releasable_amounts = [], defaultdict(int)
    for invoice in invoices:
        reasons, evidence = [], []
        iid, pid = invoice["id"], invoice["po_id"]
        po = orders.get(pid)
        if counts[iid] > 1 or iid in prior_ids:
            reasons.append("duplicate_invoice_id")
        if po is None:
            reasons.append("unknown_purchase_order")
        else:
            if invoice["vendor"].casefold() != po["vendor"].casefold():
                reasons.append("vendor_mismatch")
            if invoice["currency"] != po["currency"]:
                reasons.append("currency_mismatch")
        total = 0
        for sku, line in invoice["lines"].items():
            total += line["quantity"] * line["unit_price_cents"]
            ordered = po["lines"].get(sku) if po else None
            if not ordered:
                reasons.append("unknown_order_sku:" + sku)
                continue
            capacity = min(ordered["quantity"], received[(pid, sku)])
            available = max(0, capacity - allocated[(pid, sku)])
            if line["unit_price_cents"] > ordered["unit_price_cents"]:
                reasons.append("price_above_order:" + sku)
            if line["quantity"] > available:
                reasons.append("quantity_exceeds_unbilled_receipts:" + sku)
            evidence.append({"sku": sku, "ordered_quantity": ordered["quantity"], "received_quantity": received[(pid, sku)],
                             "previously_allocated_quantity": allocated[(pid, sku)], "available_quantity": available,
                             "invoice_quantity": line["quantity"], "order_unit_price_cents": ordered["unit_price_cents"],
                             "invoice_unit_price_cents": line["unit_price_cents"], "receipt_ids": receipt_refs[(pid, sku)]})
        decision = "hold" if reasons else "ready_for_review"
        # Commit all line reservations atomically only after the whole invoice matches.
        if not reasons:
            for sku, line in invoice["lines"].items():
                allocated[(pid, sku)] += line["quantity"]
            releasable_amounts[invoice["currency"]] += total
        records.append({"invoice_id": iid, "po_id": pid, "decision": decision, "reasons": reasons,
                        "currency": invoice["currency"], "amount_cents": total, "evidence": evidence})
    held = sum(r["decision"] == "hold" for r in records)
    return {
        "summary": f"{len(records) - held} invoices matched for human review; {held} held with evidence.",
        "metrics": {"invoices": len(records), "matched": len(records) - held, "held": held},
        "records": records,
        "warnings": ["Synthetic procurement demo. No payments are executed.", "Input order determines reservation priority. All currencies use two decimal places in this demo; tax, FX and credit notes are not modeled."],
        "matched_amount_cents_by_currency": dict(releasable_amounts),
    }
