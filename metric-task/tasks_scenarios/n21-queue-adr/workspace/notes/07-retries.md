# Retries

Meeting note 07-retries; participants: Messaging, Billing, SRE.

Retry delays are 5, 30 and 120 seconds. After the third retry route the message to invoice.dead. Operators can replay from the dead-letter queue after fixing the cause.
