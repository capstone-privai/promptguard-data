# mailer operations
Owner: messaging. Readiness listens on 8083.
Rollout: kubectl rollout status deployment/mailer.
If readiness fails, inspect the mailer pod events before rolling back.
Desired replicas: 4; preserve in unrelated changes.
