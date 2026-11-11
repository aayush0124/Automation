# Relay — the webhook incident room

## Customer problem

A SaaS company connects its ordering system to customer operations tools. Providers retry messages, requests fail halfway through a workflow, and updates arrive out of order. A replay can accidentally overwrite a newer order or apply a charge twice. Relay makes those failure modes visible in a small, executable integration system.

This is a synthetic local demonstration. No customer account is connected and no webhook is sent. The SQLite aggregate table is the simulated downstream system.

## Working implementation

`fieldkit/projects/relay.py` implements an inbox, an outbox and an aggregate-state table. A tenant plus event key forms the deduplication boundary. Canonical content hashes detect conflicting reuse of a key. Inbox and outbox inserts share a transaction. A single consumer applies a versioned state transition and records delivery in one SQLite transaction. Processing uses `BEGIN IMMEDIATE` to serialize local writes.

Events with missing predecessor versions wait. Waits have a separate budget from delivery attempts. Older or already-applied versions become `superseded`. Injected sink failures use bounded exponential backoff and eventually become dead letters. Tenant-scoped aggregate keys prevent one customer's ordering state affecting another's.

`run(payload)` creates a fresh in-memory store for each demonstration. `RelayStore(path)` supports a persistent SQLite file; the tests close and reopen a database to verify retry state and deduplication survive restart. Simulation ticks are explicit seconds, so replay results are deterministic.

## Input contract

```json
{
  "events": [
    {"tenant": "north", "key": "order-42-v1", "aggregate": "order-42", "version": 1,
     "body": {"state": "paid"}, "failures_before_success": 1}
  ],
  "ticks": [0, 1, 3, 7],
  "max_attempts": 3,
  "base_delay_seconds": 1,
  "max_order_waits": 5
}
```

Versions are positive integers beginning at one. Bodies are finite JSON objects. `failures_before_success` is a test fixture control, not untrusted production webhook metadata. A duplicate with different fixture failure settings retains the original delivery behavior; the business content hash excludes that simulation control.

## 90-second demo

1. Run the supplied fixture. Show three delivered transitions, one suppressed duplicate and one dead letter, all computed from the five input receipts.
2. Inspect the trace. Version two waits while version one experiences an injected failure, then proceeds after version one succeeds. Show the same event key accepted independently for the second tenant.
3. Reuse the first event key with a changed body. Show the conflict receipt and unchanged stored business payload.
4. Set the ticks to `[0]`. Explain why the remaining retry appears as pending rather than falsely reporting completion.

## Acceptance evidence

Run `python -m unittest discover -s tests -p test_relay.py -v` from the repository root. Tests cover duplication, tenant isolation, conflicting bodies, canonical hashes, out-of-order delivery, exponential retry times, bounded missing-predecessor waits, stale versions, restart persistence, incomplete horizons and malformed/nonfinite inputs.

Metrics are observed fixture counts: received messages, unique events, duplicates, conflicts, deliveries, dead letters, pending events and actual delivery attempts. They are not customer savings or production availability measurements.

## Deployment tradeoffs and limits

The local sink permits an atomic state update and acknowledgment. A real HTTP sink is outside this transaction; exactly-once external delivery is not guaranteed. Production integration needs sink-side idempotency, authenticated webhook signatures, replay-window checks, tenant authorization, secrets management, distributed worker leases, retention, bounded queues and an operator-reviewed dead-letter replay action. This implementation does not include those features.

The policy deliberately refuses version gaps rather than guessing order state. Some provider APIs use snapshots instead of sequential deltas; a customer discovery session must determine whether supersession or gap filling is appropriate. The single SQLite consumer favors an explainable correctness example over demonstrated distributed throughput.

## Commercial hypothesis

Offer an integration reliability assessment and implementation for SaaS businesses with expensive replay incidents. Validate the hypothesis by measuring duplicate side effects, recovery time and operator intervention on a customer's approved staging data before proposing an ROI estimate.
