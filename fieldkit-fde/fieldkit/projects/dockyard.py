"""Deterministic customer-data import with conflict quarantine and cell lineage."""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

SPEC = {
    "id": "dockyard", "name": "Dockyard", "track": "enterprise",
    "tagline": "Messy customer exports, explainable clean records.",
    "description": "Normalize a CRM CSV, quarantine identity conflicts, and retain cell-level lineage.",
    "customer": "A customer-success team migrating two acquired CRMs",
    "skills": ["data integration", "schema mapping", "data quality", "lineage"],
    "flagship": True,
}
SAMPLE = {
    "csv": "Customer ID,Full Name,E-mail,Organisation,Country\nC-101, Mira Shah ,MIRA@example.test,Northstar Labs,in\nC-101,Mira Shah,mira@example.test,Northstar Labs,IN\nC-102,Dev Mehta,dev@example.test,Harbour Works,IN\nC-999,Dev Mehta,dev@example.test,Harbour Works,IN\nC-104,Sam Lee,not-an-email,Orbit Studio,SG\nC-105,Ana Ruiz,ana@example.test,Orbit Studio,es\n",
    "mapping": {"Customer ID": "external_id", "Organisation": "company"},
}
FIELDS = {"external_id", "name", "email", "company", "country"}
ALIASES = {
    "external_id": "external_id", "customer id": "external_id", "id": "external_id",
    "name": "name", "full name": "name", "customer name": "name",
    "email": "email", "e-mail": "email", "email address": "email",
    "company": "company", "organisation": "company", "organization": "company",
    "country": "country", "country code": "country",
}


def _normalize(field: str, value: str) -> str:
    value = " ".join(value.split())
    if field == "email":
        return value.casefold()
    if field == "country":
        return value.upper()
    return value


def run(payload: dict) -> dict:
    """Map source headers to canonical fields; never silently choose conflicting rows."""
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object.")
    source = payload.get("csv")
    mapping = payload.get("mapping", {})
    if not isinstance(source, str) or not source.strip() or len(source) > 1_000_000:
        raise ValueError("csv must contain 1 to 1,000,000 characters.")
    if not isinstance(mapping, dict) or any(not isinstance(k, str) or not isinstance(v, str) or v not in FIELDS for k, v in mapping.items()):
        raise ValueError("mapping must map source header strings to supported canonical fields.")
    try:
        rows = list(csv.reader(io.StringIO(source.lstrip("\ufeff")), strict=True))
    except csv.Error as exc:
        raise ValueError("CSV could not be parsed.") from exc
    if not rows or len(rows) > 10_001:
        raise ValueError("CSV needs a header and at most 10,000 data rows.")
    headers = [h.strip() for h in rows[0]]
    if not all(headers) or len({h.casefold() for h in headers}) != len(headers):
        raise ValueError("CSV headers must be nonempty and unique ignoring case.")
    if set(mapping) - set(headers):
        raise ValueError("mapping references a missing source header.")
    resolved = {h: mapping.get(h, ALIASES.get(h.casefold())) for h in headers}
    canonical = [v for v in resolved.values() if v]
    if len(canonical) != len(set(canonical)):
        raise ValueError("Multiple source headers map to the same canonical field.")
    if not {"email", "name"}.issubset(canonical):
        raise ValueError("Map both an email and a name column.")

    grouped: dict[str, list] = defaultdict(list)
    quarantine = []
    data_rows = 0
    for row_number, cells in enumerate(rows[1:], 2):
        if not cells or not any(c.strip() for c in cells):
            continue
        data_rows += 1
        if len(cells) != len(headers):
            quarantine.append({"row": row_number, "reasons": ["column_count_mismatch"]})
            continue
        record, lineage = {}, {}
        reasons = []
        for header, cell in zip(headers, cells):
            field = resolved[header]
            if field:
                value = _normalize(field, cell)
                record[field] = value
                lineage[field] = {"row": row_number, "column": header, "raw": cell, "normalized": value}
                if value.startswith(("=", "+", "-", "@")):
                    reasons.append("spreadsheet_formula_prefix:" + field)
        if not record["name"]:
            reasons.append("missing_name")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", record["email"]):
            reasons.append("invalid_email")
        if record.get("country") and not re.fullmatch(r"[A-Z]{2}", record["country"]):
            reasons.append("country_must_be_two_letters")
        if reasons:
            quarantine.append({"row": row_number, "reasons": reasons, "record": record, "lineage": lineage})
        else:
            grouped[record["email"]].append((row_number, record, lineage))

    accepted, duplicate_rows = [], 0
    external_emails: dict[str, set] = defaultdict(set)
    for email, group in grouped.items():
        for _, record, _ in group:
            if record.get("external_id"):
                external_emails[record["external_id"]].add(email)
    for email, group in sorted(grouped.items()):
        conflict_fields = [f for f in sorted(FIELDS) if len({r.get(f, "") for _, r, _ in group}) > 1]
        collision = any(len(external_emails[r.get("external_id", "")]) > 1 for _, r, _ in group if r.get("external_id"))
        if conflict_fields or collision:
            reasons = ["conflicting_values:" + f for f in conflict_fields]
            if collision:
                reasons.append("external_id_has_multiple_emails")
            for row_number, record, lineage in group:
                quarantine.append({"row": row_number, "reasons": reasons, "record": record, "lineage": lineage})
            continue
        first = group[0][1].copy()
        first["source_rows"] = [row[0] for row in group]
        first["lineage"] = {f: [row[2][f] for row in group] for f in first if f not in {"source_rows", "lineage"}}
        accepted.append(first)
        duplicate_rows += len(group) - 1
    quarantined = len(quarantine)
    accepted_source_rows = sum(len(r["source_rows"]) for r in accepted)
    warnings = ["The included sample is synthetic; this is a deterministic import preview, not a CRM write."]
    ignored = [h for h, target in resolved.items() if not target]
    if ignored:
        warnings.append("Unmapped source columns were ignored: " + ", ".join(ignored))
    if quarantined:
        warnings.append("Conflicting and invalid rows need review before import.")
    return {
        "summary": f"{len(accepted)} clean customers; {quarantined} rows quarantined; {duplicate_rows} duplicate rows collapsed.",
        "metrics": {"input_rows": data_rows, "clean_customers": len(accepted), "accepted_source_rows": accepted_source_rows,
                    "quarantined_rows": quarantined, "duplicates_collapsed": duplicate_rows,
                    "accepted_row_percent": round(100 * accepted_source_rows / data_rows, 1) if data_rows else 0},
        "records": accepted, "warnings": warnings,
        "quarantine": sorted(quarantine, key=lambda r: r["row"]), "resolved_mapping": resolved,
    }
