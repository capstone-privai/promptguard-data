# Worker

Owner: Messaging

Run python3 -m apps.worker --fixture for a single local job. A delivery is acknowledged only after its transaction commits. Restarting a fixture worker must not create another ledger entry.

