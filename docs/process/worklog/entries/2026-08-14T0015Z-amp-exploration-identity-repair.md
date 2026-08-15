---
date: 2026-08-14T00:15:17Z
author: Amp
kind: milestone
related:
  - docs/project/exploration/index.md
  - ES-050
  - ES-051
  - ES-052
verification:
  - Identifier inspection found 34 distinct earlier ES labels through ES-049
  - UV_FROZEN=1 uv run pytest -q tests/project/test_exploration_identity.py
  - scripts/check full, static gates and 2171 passed
  - Local links, story metadata, identifier references, and git diff --check
---

# 1 Restore one monotonic Exploration namespace

Counting visible directories reused previously allocated identifiers. Existing
references reached `ES-049`, including an earlier collision between two uses
of `ES-039` that assigned one story `ES-040`. The full interval through
`ES-049` is reserved, whether each story has a directory or not.

The three August stories received these codes:

| Opened | Story | Previous code | Canonical code |
| --- | --- | --- | --- |
| 2026-08-10 | Shared Activity execution scope | `ES-001` | `ES-050` |
| 2026-08-11 | First-class lifecycle scopes | `ES-002` | `ES-051` |
| 2026-08-13 | DeepSeek Harness plugin composition | `ES-003` | `ES-052` |

Earlier references keep their original meanings. Only these stories and their
related artifacts were renumbered. Inspection found 34 distinct earlier labels;
missing numbers do not establish that a code is available.

## 1a Allocation rule

The Exploration index owns `historical_high_water` and `next_code`. A new
story takes the next code and advances it in the same commit. Story directories
own lifecycle state and remain after archive or drop. Codes are never reused.
The first story accepted into the target branch keeps its code when concurrent
work collides; the incoming story receives the next code and records the mapping.

## 1b Verification and follow-up

The focused project test passed, and `scripts/check full` passed static checks
and all 2,171 tests. Relative links, metadata, identifier references, and
whitespace checks passed. The next code at this milestone was `ES-053`.
Preserve both allocation fields and never infer a new code from directory count.
