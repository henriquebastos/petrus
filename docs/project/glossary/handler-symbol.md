# Handler symbol

A scoped name declared in the net schema identifying the handler
expected by a transition, mapped to a concrete implementation before
the process can run. A transition without one is default-bound to the
pure `passthrough` handler.

- Detail: [spec/handler-contract.md](../../../spec/handler-contract.md)
