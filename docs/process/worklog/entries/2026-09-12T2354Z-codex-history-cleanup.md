---
date: 2026-09-12T23:54:05Z
author: codex
kind: milestone
verification:
  - Complete Git object scan, case-insensitive
  - All 141 original commits compared with their rewritten counterparts
  - Python AST comparison excluding module docstrings
  - Telemetry tests, 51 passed with no skips
  - git fsck --full --strict
---

# 1 Prepare a history cleanup

The Navigator requested removal of an external project name from Git history.
The audit found two file versions containing the name, both present since the
root commit. The affected paths were `src/petrus/telemetry.py` and
`tests/petrus/telemetry/test_telemetry.py`. Paths, ref names, and commit metadata
had no matches. The remote advertised two branches and no tags.

## 1a Candidate and verification

A separate mirror clone contains the cleanup. The rewrite removes the two
derivation passages while preserving the remaining telemetry documentation.
All 141 commit IDs change. File paths, modes, all other file contents, commit
messages, authors, timestamps, and parent relationships remain unchanged.
Python AST comparison confirms that executable code remains unchanged.

The candidate scan covered 1,961 blobs, 1,638 trees, and 141 commits before
this record. It found zero matches. All 51 telemetry tests passed with skips
forbidden. The full application suite was not run for this docstring cleanup.
Git integrity checks passed. No refactoring or technical debt change was needed.

## 1b Publication remains pending

The Driver recommends accepting the verified candidate. Remote publication
requires explicit approval for both branch replacements under project Rule 13.
This record does not claim that publication or local checkout cleanup occurred.

| Branch | Original tip | Rewritten tip before this record |
| --- | --- | --- |
| `main` | `160174fcb22d2082baa95ec9ad45d53813908859` | `f86930c4c04295d533afb346159579d9e00c06aa` |
| `experiment/activity-scopes` | `6e89b502acbe95009858451ef0b470d7c3a66b14` | `d5f06b8a021f28f40e0ff024f6222dbc8086f239` |

After approval, recheck remote tips and use one atomic push with explicit
leases for both branches. Stop if either original tip has changed. Reconcile
the local checkout and its old refs separately after successful publication.

The operator's recovery bundle, candidate clone, verification script, and
commit map are outside the project under
`/Users/henrique/.cache/petrus-history-cleanup/20260912T235405Z/`.
The recovery bundle and original checkout retain the old content. Other
clones and server-retained objects are outside the candidate's verification.
References to historical commit IDs in file contents remain unchanged.
