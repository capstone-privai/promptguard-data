# Observability

Owner: SRE

The ledger-local dashboard groups failures by request ID. Check queue_age_seconds before scaling consumers. If the oldest message exceeds 120 seconds, open an incident rather than silently purging the queue.

