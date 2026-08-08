---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0029
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0029: Arc identity uses endpoint URI with optional fragment

## Status

Accepted

## Context

ADR 0026 accepted typed URI schemes for graph citizens:

```txt
place:/review/pending
transition:/review/start
arc:/review/pending->/review/start
```

The endpoint-shaped arc URI works well when there is only one arc between a given pair of endpoints. However, Petrus should allow multiple arcs between the same place and transition when those arcs represent different semantics, such as consume, read, and inhibit relationships or different token colors/cardinalities.

Example duplicate endpoint pair:

```txt
place:/review/pending
transition:/review/start
```

Possible arcs:

```txt
consume ReviewRequest x 1
read UserContext x 1
inhibit InProgress x 1
```

All share the same base endpoint URI:

```txt
arc:/review/pending->/review/start
```

Petrus needs a stable way to identify them without making every arc require a name.

## Decision

Multiple arcs between the same endpoints are allowed.

The canonical arc URI is endpoint-derived. If the endpoint pair is unique, the arc may use the base URI:

```txt
arc:/review/pending->/review/start
```

If multiple arcs share the same endpoints, the arc URI uses a fragment to disambiguate:

```txt
arc:/review/pending->/review/start#claim-review
```

Authoring APIs may allow optional arc IDs. If an arc ID is provided, it becomes the URI fragment.

If no arc ID is provided and disambiguation is needed, composition/flattening assigns a deterministic generated fragment:

```txt
arc:/review/pending->/review/start#$0
arc:/review/pending->/review/start#$1
```

The generated fragment must be deterministic for the same composed source net.

## Consequences

- Arc identity remains visually tied to directed endpoints.
- Users do not need to name every arc.
- Users can name arcs when diagnostics, tooling, source maps, or repeated endpoint pairs benefit from stable readable identity.
- Duplicate endpoint arcs are supported without forcing semantic fields into the URI query string.
- Arc URI identity does not depend directly on mode/color/cardinality, so changing an inscription does not necessarily change the arc's identity.
- Generated fragments may still be affected by source edits; stable public references should use explicit arc IDs.

## Fragment meaning

For `arc:` URIs, the fragment identifies the arc when endpoint-derived identity is ambiguous:

```txt
arc:/review/pending->/review/start#claim-review
```

For `place:` and `transition:` URIs, fragments address anchored declarations:

```txt
transition:/review/start#handler
transition:/review/start#guard:isReady
place:/review/pending#initial
```

The fragment is interpreted according to the URI scheme.

## Examples

Unique endpoint pair:

```txt
arc:/review/requested->/review/load-pr
```

Repeated endpoint pair with explicit IDs:

```txt
arc:/review/pending->/review/start#claim-request
arc:/review/pending->/review/start#read-context
arc:/review/pending->/review/start#no-in-progress
```

Repeated endpoint pair with generated fallback:

```txt
arc:/review/pending->/review/start#$0
arc:/review/pending->/review/start#$1
arc:/review/pending->/review/start#$2
```
