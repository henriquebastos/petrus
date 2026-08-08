---
status: Decided
raised: 2026-08-08
decided: 2026-08-08
deciders:
  - Henrique (Navigator)
related:
  - LICENSE-SCOPE.md
  - THIRD_PARTY_NOTICES.md
---

# 1 Source and documentation scope

Petrus support claims must be understandable and verifiable from its source,
tests, specifications, and publicly reachable authoritative references.
Technical decisions explain the runtime's current shape. Roadmap records
identify unfinished work, and debt items describe costs carried by the source.

## 1a Contribution requirements

- A maintained example needs an owner, a support claim, and an executable
  release check.
- Experimental applications have their own scope and acceptance evidence.
- Documentation must state the evidence and limits of each support claim.
- Vendored or captured third-party material requires a path-level rights
  review and the applicable license notice.
- The complete test gate forbids skips. Separately marked external
  qualification tests are explicitly deselected.

## 1b Review trigger

Review these requirements when adding a maintained example, vendored source,
or a supported capability that needs another form of validation.
