"""Deterministic, purpose-bound text minimization and a deny-by-default egress gate.

This is a bounded engineering demonstration, not comprehensive PII detection or
a determination of legal consent. Character offsets refer to the original text.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any


SPEC = {
    "id": "consentline",
    "name": "ConsentLine",
    "track": "enterprise",
    "tagline": "Give a workflow the minimum data it is allowed to use.",
    "description": "Purpose-bound redaction, keyed pseudonyms, span-level evidence and a fail-closed egress decision for synthetic support text.",
    "customer": "A support platform sharing ticket excerpts with an external analysis vendor",
    "skills": ["data minimization", "policy enforcement", "HMAC pseudonyms", "audit trails", "failure handling"],
    "flagship": False,
}

# These are demonstration product policies, not rules derived from legislation.
PURPOSE_POLICIES = {
    "support_summary": frozenset(),
    "contact_reply": frozenset({"email", "phone"}),
    "tax_review": frozenset({"pan"}),
    "aggregate_analytics": frozenset(),
}
DATA_CLASSES = frozenset({"email", "phone", "pan"})
MAX_TEXT_LENGTH = 100_000

SAMPLE = {
    "text": "Synthetic ticket: reply to mira@example.test or +91 98765 43210. PAN-like identifier ABCDE1234F was pasted by mistake. Repeated contact: mira@example.test.",
    "purpose": "support_summary",
    "consent": {"granted": True, "purposes": ["support_summary"], "data_classes": []},
    "keep_classes": [],
    "mode": "pseudonymize",
    "pseudonym_key": "synthetic-public-demo-key-not-for-production",
}

_PATTERNS = (
    ("email", re.compile(r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}(?![\w-])", re.I)),
    ("pan", re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", re.I)),
    ("phone", re.compile(r"(?<![\w])\+?[0-9](?:[0-9 ().-]*[0-9])(?![\w])")),
)


def _string_set(value: Any, label: str, allowed: frozenset[str] | None = None) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    result = set(value)
    if allowed is not None and not result <= allowed:
        raise ValueError(f"{label} contains an unsupported value")
    return result


def _validate(payload: Any) -> tuple[str, str, dict[str, Any], set[str], str, bytes | None]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"text must contain between 1 and {MAX_TEXT_LENGTH} characters")
    purpose = payload.get("purpose")
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("purpose must be a non-empty string")
    consent = payload.get("consent")
    if not isinstance(consent, dict) or not isinstance(consent.get("granted"), bool):
        raise ValueError("consent must be an object with a boolean granted field")
    _string_set(consent.get("purposes"), "consent.purposes")
    _string_set(consent.get("data_classes"), "consent.data_classes", DATA_CLASSES)
    keep = _string_set(payload.get("keep_classes", []), "keep_classes", DATA_CLASSES)
    mode = payload.get("mode", "redact")
    if mode not in ("redact", "pseudonymize"):
        raise ValueError("mode must be redact or pseudonymize")
    key = None
    if mode == "pseudonymize":
        raw_key = payload.get("pseudonym_key")
        if not isinstance(raw_key, str) or len(raw_key.encode("utf-8")) < 16:
            raise ValueError("pseudonymize requires a pseudonym_key of at least 16 UTF-8 bytes")
        if len(raw_key.encode("utf-8")) > 4096:
            raise ValueError("pseudonym_key must not exceed 4096 UTF-8 bytes")
        key = raw_key.encode("utf-8")
    return text, purpose, consent, keep, mode, key


def detect(text: str) -> list[dict[str, Any]]:
    """Return non-overlapping matches; raw values never leave the transformation.

    Email wins over an embedded PAN-shaped substring. Phone candidates require
    10-15 digits. Longer numeric spans are ambiguous and block egress rather
    than silently discarding potentially adjacent phone numbers.
    """
    candidates = []
    for priority, (data_class, pattern) in enumerate(_PATTERNS):
        for match in pattern.finditer(text):
            digits = len(re.sub(r"\D", "", match.group())) if data_class == "phone" else 0
            if data_class == "phone" and digits < 10:
                continue
            candidates.append((priority, match.start(), match.end(), data_class, digits > 15))
    accepted: list[dict[str, Any]] = []
    for _, start, end, data_class, ambiguous in sorted(candidates):
        if any(start < item["end"] and end > item["start"] for item in accepted):
            continue
        span = {"start": start, "end": end, "data_class": data_class}
        if ambiguous:
            span["ambiguous"] = True
        accepted.append(span)
    return sorted(accepted, key=lambda item: item["start"])


def _pseudonym(raw: str, data_class: str, key: bytes, purpose: str) -> str:
    if data_class == "phone":
        normalized = re.sub(r"\D", "", raw)
    elif data_class == "email":
        normalized = raw.casefold()
    else:
        normalized = raw.upper()
    # Purpose namespace limits correlation between different product workflows.
    message = f"consentline:v1:{purpose}:{data_class}:{normalized}".encode("utf-8")
    token = hmac.new(key, message, hashlib.sha256).hexdigest()[:20]
    return f"[{data_class.upper()}_{token}]"


def run(payload: dict[str, Any]) -> dict[str, Any]:
    text, purpose, consent, keep, mode, key = _validate(payload)
    consented = set(consent["data_classes"])
    permitted = PURPOSE_POLICIES.get(purpose, frozenset())
    reasons = []
    if purpose not in PURPOSE_POLICIES:
        reasons.append("UNKNOWN_PURPOSE")
    if not consent["granted"]:
        reasons.append("CONSENT_NOT_GRANTED")
    if purpose not in consent["purposes"]:
        reasons.append("PURPOSE_NOT_CONSENTED")
    if not keep <= permitted:
        reasons.append("RAW_CLASS_FORBIDDEN_FOR_PURPOSE")
    if not keep <= consented:
        reasons.append("RAW_CLASS_NOT_CONSENTED")
    spans = detect(text)
    if any(span.get("ambiguous") for span in spans):
        reasons.append("AMBIGUOUS_PHONE_SPAN")
    allowed = not reasons
    parts: list[str] = []
    records: list[dict[str, Any]] = []
    cursor = 0
    for index, span in enumerate(spans, start=1):
        raw = text[span["start"]:span["end"]]
        data_class = span["data_class"]
        retained = allowed and data_class in keep
        if retained:
            replacement = raw
            action = "retain_authorized"
            audit_replacement = "[RETAINED_BY_POLICY]"
        elif mode == "pseudonymize":
            assert key is not None
            replacement = _pseudonym(raw, data_class, key, purpose)
            action = "pseudonymize"
            audit_replacement = replacement
        else:
            replacement = f"[REDACTED_{data_class.upper()}]"
            action = "redact"
            audit_replacement = replacement
        parts.extend([text[cursor:span["start"]], replacement])
        cursor = span["end"]
        records.append({
            "entity": index,
            **span,
            "action": action,
            "replacement": audit_replacement,
            "rule": f"{purpose}/{data_class}",
        })
    parts.append(text[cursor:])
    retained_count = sum(record["action"] == "retain_authorized" for record in records)
    warnings = [
        "Synthetic demonstration: regex detectors cover only email, phone-like and PAN-like strings; names, addresses and other sensitive content may remain.",
        "Consent is supplied test data, not authenticated evidence or a legal compliance determination.",
    ]
    if mode == "pseudonymize":
        warnings.append("Pseudonyms remain linkable within this purpose and key; protect keys and apply a retention policy.")
    if not spans:
        warnings.append("No configured pattern matched; this is not proof that the text contains no personal data.")
    if not allowed:
        warnings.append("Egress denied: no transformed text is returned. No external service was called.")
    return {
        "summary": f"{'Allow' if allowed else 'Deny'} egress for {purpose}; {len(spans)} detected entities, {len(spans) - retained_count} minimized.",
        "metrics": {
            "detected_entities": len(spans),
            "minimized_entities": len(spans) - retained_count,
            "retained_entities": retained_count,
            "egress_allowed": allowed,
        },
        "records": records,
        "warnings": warnings,
        "egress": {"decision": "allow" if allowed else "deny", "reasons": reasons, "text": "".join(parts) if allowed else None},
        "policy": {
            "version": "demo-v1",
            "purpose": purpose,
            "allowed_raw_classes": sorted(permitted),
            "requested_raw_classes": sorted(keep),
            "consented_raw_classes": sorted(consented),
        },
        "offset_units": "Python Unicode code points in original text; end is exclusive",
        "executed_external_actions": 0,
    }
