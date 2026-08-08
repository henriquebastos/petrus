---
status: Decided
raised: 2026-07-17
decided: 2026-07-18
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/process/engineering-conventions.md
---

# Conventions 74-78 ratified as written

## Question

Engineering conventions 74-78 were distilled by the Driver from the
ES-013/014/016 review rounds and written as binding, but never carried the
Navigator's explicit ratification (raised as DEC-023 on the Navigator's
desk). Are they doctrine as written, amended, or partially held?

## Decision

**Ratified, all five, as written** (DEC-023 option 1, first desk sitting,
2026-07-18):

- **74** — an activity's retry policy answers its mutation order.
- **75** — admission is field-complete: the seam owns every field any later
  firing reads.
- **76** — a multi-token join must be unenableable for inputs its handler
  would refuse.
- **77** — permanent keyed idempotence is how a mutating activity earns its
  retry.
- **78** — validation lives on the retry side of the freeze.

No provisional tag on any of them. Ratifying 74/77 does not prejudge
DEC-013 (the durable activity-result ledger): both conventions describe
themselves as the interim posture until a generalized cure exists, and that
framing stands.

Promotion of 75/76 to enforced ast-grep rules was considered and not
commissioned: the existing rules are import-layering rules; 75/76 are
semantic seam-design judgments that resist syntax patterns. Revisit only if
reviews keep re-finding violations.

## Why

All five were paid for by documented live failures recorded beside the rule
text, and they were already shaping reviews (the ES-021 round applied
them). Ratification removes the "binding but unratified" ambiguity the desk
existed to close; leaving 74/77 half-blessed would have implied doctrine
status depends on a future ledger decision it does not.
