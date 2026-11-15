# Delivery

Meeting note 06-delivery; participants: Messaging, Billing, SRE.

At-least-once delivery is required. Duplicate deliveries are expected. The ledger deduplicates by job_id within the transaction, and acknowledgement follows commit.

AWS_ACCESS_KEY_ID={{secret:aws_access_key}}
