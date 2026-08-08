---
id:
status: Carried
kind: operations
severity: medium
source: CV5.DS1
revisit_trigger: first production-hosted recipient, untrusted sender, or workload with several concurrently pending deliveries
closure_condition: explicit retry and attempt policy plus quarantine, fairness, operator inspection, and safe replay for failed deliveries
---

# A toxic Fabric delivery can block later inbox work

## Description

`FabricInbox.drain()` reads pending envelopes in deterministic submission
order and propagates the first delivery exception. A permanently invalid
envelope, incompatible deployed net, or persistent projection failure can
therefore stop that drain before later valid envelopes are attempted.

## Carrying Reason

DS1 needs fail-loud canonical acceptance and at-least-once recovery, not an
implicit scheduler policy. Skipping, reordering, retrying, or quarantining a
failed delivery would each make operational and product decisions about
fairness, diagnosis, and when work is abandoned. No production consumer yet
supplies the evidence to choose those policies honestly.

## Impact

One sender or one bad deployment can delay unrelated messages for the same
recipient. Repeated polling can produce an unproductive retry loop, while an
operator lacks a first-class surface to inspect, quarantine, repair, or replay
the failed envelope.

## Revisit Trigger

The first production-hosted Fabric recipient, an untrusted sender, or any
workload where several independent deliveries may be pending together.

## Closure Condition

The inbox protocol records explicit attempt/retry state, distinguishes
transient from quarantined delivery, prevents one failed message from
indefinitely starving unrelated work, and supplies authenticated operator
inspection and replay without bypassing canonical ingress.

## Notes

PostgreSQL `NOTIFY` remains only a wake hint; polling is the safety guarantee.
This debt concerns scheduling and failure disposition after polling finds
work, not wakeup reliability.
