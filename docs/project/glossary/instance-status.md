# Instance status

A derived, four-valued projection over a net instance's recorded
history — never stored as independent truth: RUNNING while not
quiescent; when quiescent, COMPLETED, AWAITING, or STUCK (or the
neutral TERMINATED when no completion condition is declared).

- Detail: [spec/firing-semantics.md](../../../spec/firing-semantics.md)
