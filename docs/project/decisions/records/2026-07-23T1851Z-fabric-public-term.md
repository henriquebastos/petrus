---
status: Decided
raised: 2026-07-23
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - exact “Process Fabric” naming clause in 2026-07-20 process-fabric-is-an-inter-authority-protocol-plane
related:
  - docs/project/decisions/records/2026-07-20T1114Z-process-fabric-is-an-inter-authority-protocol-plane.md
  - docs/project/decisions/records/2026-07-23T1805Z-engine-is-concrete-and-provider-neutral.md
---

# Choose the public term for the inter-Instance Fabric

## Question

Should the inter-Instance protocol plane's exact public product term be
**Fabric**, or should **Process Fabric** remain the formal term with Fabric as
its accepted short form? What, if anything, should the current story say about
**Weaver**?

The behavior is already decided: this protocol state routes addressed
deliveries, receipts, discovery, grants, retries, reply routes, and correlation
between distinct Instances. It owns no Engine, Instance, canonical History,
Worker, process lifecycle, or cross-Instance transaction.

## Decision

**Fabric** is the exact public capability term. Keep the already-canonical
`impetus.fabric` package and concrete `PostgresFabric` provider name. Process
`call` and `spawn` remain lifecycle concepts above Fabric; Fabric does not own
process identity or lifecycle.

This decision supersedes only the exact “Process Fabric” naming clause in the
2026-07-20 layer decision. That record's inter-Instance protocol behavior,
dependency direction, and host separation remain decided and unchanged.

Do not use **Weaver** for Fabric, and do not reserve or reject it. It remains an
unruled possible future name for an active multi-Engine host or supervisor.

## Rationale

The original CV5 decision adopted “Process Fabric” while the physical package
and most executable values use the shorter `impetus.fabric`/`Fabric` spelling.
Subsequent ontology convergence made Instance—not process—the formal durable
semantic identity, and process `call`/`spawn` became a separate lifecycle layer
above the protocol plane. That makes the word “Process” potentially redundant
or misleading in the lower layer's formal name.

The prior Navigator discussion recommended **Fabric** provisionally. Oracle
review of the implementation plan recommended the more conservative
alternative: retain **Process Fabric** formally while accepting **Fabric** as
the short form. The Navigator chose Fabric at the CV5.TS2 Plan Checkpoint.

“Weaver” describes a potentially active host or supervisor more naturally than
this passive protocol plane. No such host exists, and this decision does not
reserve, adopt, or reject that future name.

## Options Considered

### A — Fabric is the exact public term (current provisional recommendation)

Use **Fabric** in current product, roadmap, glossary, and decision prose. Keep
the already-canonical `impetus.fabric` package and concrete `PostgresFabric`
provider name. Continue to call `call` and `spawn` **process lifecycle** above
Fabric. Amend only the old term; preserve the 2026-07-20 layer and behavior
ruling.

This makes the capability name match its package and avoids implying that
Fabric owns process identity or lifecycle.

### B — Process Fabric remains formal; Fabric is the accepted short form

Keep **Process Fabric** in formal architecture prose and explicitly accept
**Fabric** as the short form and package name. Make no broad terminology edit.

This minimizes documentary churn and keeps continuity with the original CV5
decision, at the cost of retaining “Process” in a layer below process
lifecycle and after Instance became the formal durable identity.

### Weaver

Do not choose **Weaver** for the protocol plane in either option. Leave it as
an unruled possible name for a future active multi-Engine host/supervisor. This
is a deferral, not a reservation or rejection.

## Consequences

CV5.TS2 updates the current authoritative terminology surfaces and cross-links
the older record without rewriting its historical behavior rationale. It does
not mechanically rewrite historical evidence, rename the `impetus.fabric`
package, change wire/schema values, or introduce a Weaver implementation.

Fabric remains outside Engine under either term. Several Engines continue to
host distinct Instances and Histories; Fabric connects them only through
identified delivery and Activity effects.

## Review Trigger

Review only if a second transport or a real active
multi-Engine host demonstrates that the protocol and hosting concepts need a
different split.
