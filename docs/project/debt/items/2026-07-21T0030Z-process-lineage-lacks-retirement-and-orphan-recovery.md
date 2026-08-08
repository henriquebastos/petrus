---
id:
status: Carried
kind: operations
severity: medium
source: CV5.DS2
revisit_trigger: first long-lived hosted process consumer or production Authority Host
closure_condition: authenticated explicit retirement and orphan-recovery protocols with safe lineage, address, credential, and child-authority disposition
---

# Durable process lineage lacks retirement and orphan recovery

## Description

DS2 intentionally makes a `(parent, spawn_id)` lineage claim permanent and
retryable. It does not retire or unregister child addresses, prune lineage,
detect abandoned partial provisioning, revoke child credentials, collect
orphans, or define parent/child cascade behavior.

## Carrying Reason

Automatic deletion would be less safe than a durable partial claim: an
external provisioner may have created a child address or host immediately
before a crash. Without a real long-lived host consumer, the project lacks
evidence for ownership, retention, cancellation, and operator-recovery policy.
DS2 therefore preserves evidence and allows exact `ensure` retry rather than
guessing that an apparently incomplete child is disposable.

## Impact

Abandoned claims and process registrations can accumulate. Changed content
cannot reuse the same spawn identity, and operators have no first-class way to
inspect, resume, retire, or safely remove a partially provisioned child.
Long-lived deployments also lack explicit credential revocation and cascade
semantics when a parent retires.

## Revisit Trigger

The first long-lived hosted process consumer, production Authority Host, or
operational requirement to retire, replace, or recover a child process.

## Closure Condition

The process-lifecycle layer has authenticated, observable protocols for
retirement and orphan recovery; each operation defines safe disposition of
lineage, Fabric address/grants, private credentials, and child authority state;
and crash tests prove that recovery cannot delete a live child or create a
second identity.

## Notes

Call timeout and cancellation may share some future lifecycle vocabulary but
are not assumed to require deletion of spawn lineage.
