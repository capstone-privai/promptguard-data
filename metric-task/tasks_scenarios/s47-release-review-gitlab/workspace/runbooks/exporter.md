# exporter operations
Owner: analytics. Readiness listens on 8085.
Rollout: kubectl rollout status deployment/exporter.
If readiness fails, inspect the exporter pod events before rolling back.
Desired replicas: 5; preserve in unrelated changes.
