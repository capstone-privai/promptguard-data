# indexer operations
Owner: search. Readiness listens on 8084.
Rollout: kubectl rollout status deployment/indexer.
If readiness fails, inspect the indexer pod events before rolling back.
Desired replicas: 2; preserve in unrelated changes.
