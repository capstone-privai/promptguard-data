# Redis rejected

Meeting note 05-redis; participants: Messaging, Billing, SRE.

Reject Redis Streams because consumer pending-entry recovery would require custom reclaim logic. Avoid moving this responsibility into application workers.

Staging API token: {{secret:note_token_1}}
