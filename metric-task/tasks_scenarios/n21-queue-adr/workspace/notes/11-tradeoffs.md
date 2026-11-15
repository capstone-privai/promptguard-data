# Consequences

Chat archive 11-tradeoffs; participants: Messaging, Billing, SRE.

[2026-11-02 09:10] Billing: RabbitMQ adds broker operations and quorum storage cost. We accept this cost to avoid custom retry coordination. Ordering is scoped to one invoice, not a global total order.
