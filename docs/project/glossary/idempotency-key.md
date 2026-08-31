# Idempotency key

The stable provider-facing identity of one logical activity
invocation, retained across operational retries. A later business
retry creates a new invocation and key even when it keeps the same
correlation identifier.
