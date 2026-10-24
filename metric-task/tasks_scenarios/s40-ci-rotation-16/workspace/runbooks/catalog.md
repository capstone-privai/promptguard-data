# catalog operations
Owner: commerce. Readiness listens on 8081.
Rollout: kubectl rollout status deployment/catalog.
If readiness fails, inspect the catalog pod events before rolling back.
Desired replicas: 3; preserve in unrelated changes.
