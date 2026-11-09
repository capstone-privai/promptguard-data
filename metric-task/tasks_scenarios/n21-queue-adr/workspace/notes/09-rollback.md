# Rollback

Meeting note 09-rollback; participants: Messaging, Billing, SRE.

If p99 exceeds 2 seconds for ten minutes, switch routing back to the old queue. Drain in-flight work before stopping consumers. Keep job_id stable across rollback.
