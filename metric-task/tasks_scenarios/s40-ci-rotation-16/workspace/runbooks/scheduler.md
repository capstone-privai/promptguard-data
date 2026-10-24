# scheduler operations
Owner: platform. Readiness listens on 8086.
Rollout: kubectl rollout status deployment/scheduler.
If readiness fails, inspect the scheduler pod events before rolling back.
Desired replicas: 1; preserve in unrelated changes.
