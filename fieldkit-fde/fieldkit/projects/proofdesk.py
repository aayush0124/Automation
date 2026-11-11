"""Tenant- and role-scoped lexical evidence retrieval, without generated claims."""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date

SPEC = {
    "id": "proofdesk", "name": "ProofDesk", "track": "enterprise",
    "tagline": "Evidence that respects the permission boundary.",
    "description": "Resolve document versions, enforce tenant and role access, rank lexical evidence, or abstain.",
    "customer": "An enterprise support team searching conflicting customer policies",
    "skills": ["retrieval", "authorization boundaries", "versioning", "abstention", "evaluation"],
    "flagship": True,
}
SAMPLE = {
    "tenant": "northstar", "roles": ["support"], "query": "How long is the refund window?",
    "as_of": "2026-11-11", "max_age_days": 180, "limit": 3,
    "documents": [
        {"id": "refund-policy", "tenant": "northstar", "roles": ["support", "finance"], "version": 1,
         "updated_at": "2026-08-01", "title": "Refund policy v1", "text": "The refund window is 14 days after purchase."},
        {"id": "refund-policy", "tenant": "northstar", "roles": ["support", "finance"], "version": 2,
         "updated_at": "2026-10-20", "title": "Refund policy v2", "text": "The refund window is 30 days after purchase. Approved refunds return to the original payment method."},
        {"id": "private-refunds", "tenant": "northstar", "roles": ["finance"], "version": 1,
         "updated_at": "2026-10-21", "title": "Private exception budget", "text": "Refund window exceptions have a confidential finance-only budget."},
        {"id": "refund-policy", "tenant": "harbour", "roles": ["support"], "version": 1,
         "updated_at": "2026-10-22", "title": "Harbour refunds", "text": "The refund window is 90 days for Harbour customers."},
        {"id": "legacy-guide", "tenant": "northstar", "roles": ["support"], "version": 1,
         "updated_at": "2025-01-01", "title": "Expired guide", "text": "Refund window: 60 days."},
    ],
}
STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to", "was", "what", "when", "where", "which", "who", "with"}


def _tokens(value: str) -> list[str]:
    return [t for t in re.findall(r"\b\w+\b", value.casefold()) if t not in STOP and len(t) > 1]


def _day(value, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(label + " must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(label + " must be an ISO date.") from exc


def run(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object.")
    tenant, roles, query = payload.get("tenant"), payload.get("roles"), payload.get("query")
    if not isinstance(tenant, str) or not tenant.strip():
        raise ValueError("tenant must be a nonempty string.")
    if not isinstance(roles, list) or not all(isinstance(r, str) and r.strip() for r in roles):
        raise ValueError("roles must be a list of nonempty strings.")
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must contain 1 to 2,000 characters.")
    as_of = _day(payload.get("as_of"), "as_of")
    max_age, limit = payload.get("max_age_days", 365), payload.get("limit", 3)
    if type(max_age) is not int or not 0 <= max_age <= 3650 or type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("max_age_days must be 0..3650 and limit must be 1..10.")
    documents = payload.get("documents")
    if not isinstance(documents, list) or len(documents) > 1000:
        raise ValueError("documents must be a list with at most 1,000 entries.")
    versions, seen = {}, set()
    for doc in documents:
        if not isinstance(doc, dict) or any(not isinstance(doc.get(k), str) or not doc[k].strip() for k in ("id", "tenant", "title", "text")):
            raise ValueError("Every document needs nonempty id, tenant, title and text.")
        if len(doc["text"]) > 100_000 or type(doc.get("version")) is not int or doc["version"] < 1:
            raise ValueError("Document text is too long or version is not a positive integer.")
        if not isinstance(doc.get("roles"), list) or not all(isinstance(r, str) and r.strip() for r in doc["roles"]):
            raise ValueError("Document roles must be a list of nonempty strings.")
        updated = _day(doc.get("updated_at"), "updated_at")
        key = (doc["tenant"], doc["id"], doc["version"])
        if key in seen:
            raise ValueError("A document version must be unique within its tenant.")
        seen.add(key)
        if doc["tenant"] != tenant or updated > as_of:
            continue
        # Resolve newest version BEFORE checking role ACL: old access must not survive revocation.
        old = versions.get(doc["id"])
        if old is None or doc["version"] > old["version"]:
            versions[doc["id"]] = doc
    eligible = [d for d in versions.values() if set(roles).intersection(d["roles"]) and (as_of - _day(d["updated_at"], "updated_at")).days <= max_age]
    terms = set(_tokens(query))
    tokenized = {d["id"]: Counter(_tokens(d["title"] + " " + d["text"])) for d in eligible}
    scored = []
    for doc in eligible:
        counts = tokenized[doc["id"]]
        matched = terms.intersection(counts)
        if not matched:
            continue
        # Transparent lexical rank, not calibrated confidence or semantic similarity.
        score = sum((1 + math.log(counts[t])) * (1 + math.log((len(eligible) + 1) / (1 + sum(t in c for c in tokenized.values())))) for t in matched)
        score = score * (len(matched) / len(terms)) / math.sqrt(max(1, sum(counts.values())))
        sentences = re.split(r"(?<=[.!?])\s+|\n+", doc["text"])
        excerpt = max(sentences, key=lambda s: (len(terms.intersection(_tokens(s))), -len(s)))[:600]
        scored.append({"citation": doc["id"] + "@v" + str(doc["version"]), "document_id": doc["id"],
                       "title": doc["title"], "version": doc["version"], "updated_at": doc["updated_at"],
                       "excerpt": excerpt, "matched_terms": sorted(matched), "lexical_score": round(score, 6)})
    scored.sort(key=lambda d: (-d["lexical_score"], d["citation"]))
    records = scored[:limit]
    abstained = not records
    return {
        "summary": "Abstained: no fresh, authorized lexical evidence matched." if abstained else f"Found {len(records)} fresh, authorized evidence excerpts.",
        "metrics": {"returned_citations": len(records), "query_terms": len(terms), "abstained": abstained},
        "records": records, "warnings": ["Lexical retrieval only; excerpts are untrusted source text, not instructions or a generated answer.",
                                                "Identity and document ACLs are supplied for this local demo. Production must derive both from trusted systems."],
        "abstained": abstained, "answer_mode": "evidence_only", "as_of": as_of.isoformat(),
    }
