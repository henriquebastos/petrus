# Worker instance

A running process replica of a Worker definition, with an ephemeral
incarnation per process boot. Motus requires no durable Worker
Registry: queue polling offers capacity, DevOps owns process
lifecycle, and Dispatch owns correctness-critical Attempt leases.
