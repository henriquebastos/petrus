---
historical_high_water: ES-049
next_code: ES-053
---

# Exploration

Exploratory Stories preserve architecture inquiries that need evidence before
they become delivery commitments. Each story owns its current inquiry,
alternatives, experiments, evidence, and disposition in one self-contained
directory. A candidate becomes implementation work only after the evidence
supports a bounded change.

## Identifier continuity

Exploratory Story codes form one repository-global, monotonic namespace. A code
is allocated once and never reused, including when its story is completed,
promoted, paused, archived, dropped, or
administratively renumbered after a collision.

Existing references use identifiers through `ES-049`. The entire `ES-001`
through `ES-049` interval remains reserved. Story directories begin at
`ES-050`; a missing directory does not release its code for reuse.

`historical_high_water` preserves the historical reservation. `next_code` is
the next code to allocate, not a directory count. When opening a story:

1. use the exact `next_code` value in the story directory and frontmatter;
2. advance `next_code` in the same commit that introduces the story; and
3. keep the story directory as a tombstone with explicit status if the story
   later leaves the active Narrative Field.

Never derive a code from the number of visible directories, renumber historical
references to close a gap, or delete a story to release its code. If concurrent
work claims the same code, the first claim accepted into the target branch
keeps it; renumber the incoming story to the next available code and preserve
the administrative mapping in its worklog or story timeline.

[`test_exploration_identity.py`](../../../tests/project/test_exploration_identity.py)
checks that directory and frontmatter codes agree, no code above the reservation is
missing or duplicated, and `next_code` follows the highest retained story. The
[2026-08-14 identity repair](../../process/worklog/entries/2026-08-14T0015Z-amp-exploration-identity-repair.md)
records the historical audit and the one-time `ES-001`–`ES-003` to
`ES-050`–`ES-052` mapping.

## Structure

```text
docs/project/exploration/
  index.md
  es-<code>-<story-slug>/
    index.md
    experiments/                 # only when needed
    artifacts/                   # only when needed
```

State belongs in each story's metadata, not in this index or primarily in its
directory path. Find active work by searching story indexes for `status`.
