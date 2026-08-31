# Worker definition

Motus deployment configuration naming the operational queues a Worker
subscribes to and the Activity implementations it can execute, plus
concurrency and polling. A Worker imports Activity implementations,
not a runnable Net definition, and does not invent retry, idempotency,
routing, or reconciliation policy.
