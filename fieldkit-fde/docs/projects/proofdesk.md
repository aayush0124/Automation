# ProofDesk — permission-aware evidence retrieval

## Customer discovery brief

An enterprise support team needs to find the correct refund policy while several customers, departments and policy versions share the same workspace. A polished answer is harmful if it uses another tenant's policy, retrieves a finance-only exception, or resurrects a version whose access was revoked.

**Discovery questions:** Where does identity come from? Which system owns ACLs? Does policy publication time differ from effective time? How should deletions and revoked access propagate? What evidence is sufficient for a support agent to answer, and when must the product abstain?

## Working implementation

`fieldkit/projects/proofdesk.py` implements a deterministic evidence layer, not an LLM chatbot. It validates document versions, filters by tenant and historical date, selects the highest available version of each document, and only then applies role and freshness rules. Resolving versions **before** role filtering prevents fallback to an older version after access was revoked.

The remaining documents are ranked using transparent lexical term matching with frequency and corpus rarity weighting. Results include versioned citation IDs, dates, matched terms and source excerpts. No authorized match means an explicit abstention. Scores are ranking signals, not confidence probabilities. The system does not invent an answer or execute document text as instructions.

| Boundary | Implemented behavior | Production dependency |
|---|---|---|
| Tenant | Exact tenant match before retrieval | Verified identity and tenant claims |
| Role | At least one supplied role intersects the current document ACL | ACL sync from the authoritative source |
| Version | Highest published version available as of the supplied date | Source-specific publication/effective-time semantics |
| Freshness | Documents older than the allowed age are excluded | Owner-specific review and expiry policies |
| Evidence | Excerpts and citations only; abstention on no lexical match | Optional evaluated generation grounded in these excerpts |

## Minimal input

```json
{
  "tenant": "northstar",
  "roles": ["support"],
  "query": "refund window",
  "as_of": "2026-11-11",
  "max_age_days": 180,
  "limit": 3,
  "documents": [{
    "id": "refund-policy",
    "tenant": "northstar",
    "roles": ["support"],
    "version": 2,
    "updated_at": "2026-10-20",
    "title": "Refund policy",
    "text": "The refund window is 30 days after purchase."
  }]
}
```

Bundled policies, organizations and identities are synthetic. For this local demo, both identity and ACLs arrive in the request. That illustrates policy logic but does **not** authenticate a user: a production service must not trust client-provided roles or tenant claims.

## 90-second interview demo

1. Run the bundled support query. Show the current 30-day policy citation. The old 14-day version, another tenant's 90-day policy, a finance-only document and an expired guide do not appear.
2. Change the current policy's roles to `["finance"]`. Run again. It abstains instead of returning the older support-accessible version. Explain this revoked-access regression test.
3. Restore the ACL and ask about `orbital propulsion`. It abstains. Then place an instruction-like sentence in the document text: the output remains an evidence excerpt and never accesses finance data or invokes a tool.

## Acceptance evidence

```bash
python -m unittest discover -s tests -p test_proofdesk.py -v
```

Eleven tests cover tenant isolation, role denial without title/snippet leakage, access revocation, historical version resolution, freshness exclusion, empty/unmatched queries, inert instruction text, duplicate version rejection and malformed inputs. This is a bounded test suite, not a security certification or a semantic retrieval benchmark.

## Deployment and handoff

Add SSO, server-derived identity, source ACL synchronization, deletion tombstones, persistent indexing, document provenance, audit logs, pagination and retrieval-quality datasets. Evaluate synonym-heavy and multilingual queries before replacing lexical matching with embeddings or hybrid retrieval. If adding generation, pass only authorized evidence, keep source text untrusted, require citations and measure unsupported claims and abstentions with a held-out set.

The current demo handles at most 1,000 documents per request, with 100,000 characters per document. It is stateless, English-stopword-oriented, has no embeddings, no external connectors and no autonomous actions. Citation IDs are local document/version identifiers, not clickable external sources.

**Commercial hypothesis:** deploy a controlled knowledge-search pilot for support or internal operations. Measure correct-policy retrieval, unauthorized-content leakage tests, abstention quality and operator time on a customer-approved evaluation set. No business improvement is claimed from the synthetic sample.
