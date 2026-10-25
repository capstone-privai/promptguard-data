# worker operations
Owner: fulfillment. Readiness listens on 8087.
Rollout: kubectl rollout status deployment/worker.
If readiness fails, inspect the worker pod events before rolling back.
Desired replicas: 6; preserve in unrelated changes.
