# gateway operations
Owner: edge. Readiness listens on 8080.
Rollout: kubectl rollout status deployment/gateway.
If readiness fails, inspect the gateway pod events before rolling back.
Desired replicas: 2; preserve in unrelated changes.
