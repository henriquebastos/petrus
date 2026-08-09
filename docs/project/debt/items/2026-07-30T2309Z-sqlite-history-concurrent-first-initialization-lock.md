---
id:
status: Paid
kind: test
severity: medium
source: CV9
revisit_trigger: next SqliteHistoryStore schema/connection change, another concurrent-initialization recurrence, or complete-gate reliability work
closure_condition: concurrent first initialization has a decided serialization/retry contract, passes repeatedly, and no longer destabilizes complete gates
---

# Concurrent SQLite History first initialization can surface database-locked

## Description

`tests/petrus/impetus/history_store/test_sqlite_history.py::test_concurrent_first_initialization_for_distinct_instances`
opens two `SqliteHistoryStore` instances against one previously absent database
from synchronized threads. Intermittently, one constructor raises
`sqlite3.OperationalError: database is locked` during first schema
initialization. The exact test then passes without a runtime change.

The symptom occurred in the fixed-seed serial full run during the CV9
interactive-proposal checkpoint and had appeared in an earlier unrelated
complete-suite run. It remains unclear whether production first initialization
promises transparent concurrent serialization or whether the test assumes a
stronger startup contract than supported.

## Carrying Reason

CV9 does not own History-store schema initialization or SQLite connection
policy. Adding a sleep, suppressing the test, or increasing a timeout would not
decide the production contract and would be an unrelated infrastructure
detour.

## Impact

The complete gate can alternate red and green without relevant source changes.
If the test reflects a real supported startup route, two process/thread owners
starting against a new database may expose the same lock instead of converging
on one initialized schema.

## Revisit Trigger

Revisit on the next `SqliteHistoryStore` schema/connection change, another
independent recurrence, or before release qualification treats concurrent
first initialization as guaranteed behavior.

## Closure Condition

Decide whether concurrent first initialization is a supported runtime promise.
If it is, serialize or retry schema setup under a bounded explicit policy; if
it is not, narrow the test and document the required bootstrap ownership. The
exact test and repeated complete gates must pass.

## Notes

CV9 evidence: the serial full run reported one `database is locked` failure
while all focused CV9 tests passed; the exact SQLite test passed immediately in
isolation. No SQLite History source was changed by CV9.

**Paid 2026-08-09:** synchronized reproduction located the contention at
`PRAGMA journal_mode = WAL`, before schema `BEGIN IMMEDIATE`, DDL, load, or
append ownership. `SqliteHistoryStore` now retries only a `locked`
`OperationalError` from that WAL-bootstrap pragma under a five-second monotonic
deadline; other operational errors and lock failures elsewhere retain their
original fate. The synchronized test passed 25 repeated invocations, the
14-test SQLite History surface passed, and the integrated full and release
gates passed.
