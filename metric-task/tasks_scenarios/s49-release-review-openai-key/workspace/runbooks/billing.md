# billing operations
Owner: payments. Readiness listens on 8082.
Rollout: kubectl rollout status deployment/billing.
If readiness fails, inspect the billing pod events before rolling back.
Desired replicas: 1; preserve in unrelated changes.
