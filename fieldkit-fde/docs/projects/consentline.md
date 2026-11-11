# ConsentLine

**Customer scenario:** a support platform wants to send ticket excerpts to a text-analysis vendor. A ticket often contains contact details pasted into the wrong workflow. The integration should send only the information permitted for its purpose and explain every transformation.

This project is a working, deterministic minimization engine and egress-decision demo. All bundled text, consent and keys are synthetic. It performs no external transfer and makes no legal compliance determination.

## Implemented workflow

1. Validate the text, declared purpose, consent fixture and explicit raw-field request.
2. Find email, phone-like and PAN-like spans in the original text; resolve overlapping matches deterministically.
3. Check the purpose allowlist and the separately supplied consent data-class allowlist. Unknown purposes, revoked consent and unauthorized raw-field requests deny the entire egress operation.
4. Redact unneeded identifiers or replace them with HMAC pseudonyms. The purpose, identifier class and normalized value are included in the HMAC namespace.
5. Return an allow/deny result, transformed text only when allowed, and an audit record of offsets and actions. Audit records omit original matched values and the key.

The default `support_summary` purpose permits no raw identifiers. `contact_reply` can retain explicitly requested, consented email and phone values. `tax_review` can retain explicitly requested, consented PAN-like values. `aggregate_analytics` permits no raw identifiers. These are illustrative product policies, not statutory requirements.

## Run and inspect

Use the repository dashboard to select **ConsentLine** and run the synthetic sample, or call the module directly:

```python
from fieldkit.projects.consentline import SAMPLE, run

result = run(SAMPLE)
print(result["egress"]["text"])
print(result["records"])
```

```sh
python -m unittest discover -s tests -p "test_consentline.py" -v
```

Input fields are `text`, `purpose`, `consent` (`granted`, `purposes`, `data_classes`), `keep_classes`, and `mode` (`redact` or `pseudonymize`). Pseudonym mode requires a `pseudonym_key` of at least 16 UTF-8 bytes. The public demo key is fixture data: never use it with real data. Redaction mode does not need a key.

## 90-second customer demo

- **0–25 seconds:** run the sample. Inspect four recognized spans and the repeated email's stable pseudonym. No matched original identifier appears in the result.
- **25–45 seconds:** set `keep_classes` to `["email"]` while keeping `support_summary`. Egress is denied because the purpose does not authorize raw email, even if consent lists email.
- **45–65 seconds:** change the purpose and consented purpose to `contact_reply`, authorize email in `consent.data_classes`, and retain email. Email is available to this contact workflow while phone and PAN-like text remain minimized.
- **65–90 seconds:** set `consent.granted` to `false`. The result denies egress and returns no transformed text. Point out that the demo trusts consent input; a real deployment must authenticate that evidence.

## Acceptance evidence

Tests exercise overlap precedence, Unicode offsets, repeated-identifier normalization, cross-purpose and cross-key pseudonym separation, explicit authorized retention, disallowed raw classes, missing consent, revoked consent, unknown purposes, no-match uncertainty, malformed input and input immutability. Run the command above for the measured pass/fail result rather than treating this description as test evidence.

## Boundaries and production backlog

- Regex coverage is intentionally narrow. Names, addresses, IDs from other jurisdictions, obfuscations and contextual sensitive information may pass through. A no-match result is not a safe-data certification.
- Phone detection recognizes 10–15 digits with common separators; it is not phone ownership or country validity verification. PAN detection recognizes a string pattern, not a validated government record.
- Inputs are test data, not authenticated identity or consent. A production connector needs trusted tenant identity, signed or server-held consent records, expiry/revocation handling and data retention controls.
- HMAC pseudonyms are linkable within a key and purpose. Production keys belong in a secret manager; tenant separation, rotation and key versioning require explicit design. The audit trace still reveals data classes, lengths and positions.
- Production egress must enforce the decision at the actual network boundary. This module never transmits anything. It has no persistence, encryption at rest or deployment authentication.
- The raw text and key exist in process memory during execution. The host must avoid logging request bodies and use synthetic data for its public demo.

**Commercial hypothesis:** offer a scoped support-platform integration pilot that measures disallowed-identifier escape rate and reviewer workload on a customer-approved labeled corpus. Neither accuracy nor savings is established by the synthetic fixture.
