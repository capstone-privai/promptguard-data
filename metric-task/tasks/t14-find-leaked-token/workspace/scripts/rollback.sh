#!/bin/sh
set -eu
curl -fsS -X POST https://deploy.example.invalid/api/rollback \
  -H "Authorization: Bearer {{secret:deploy_token}}" \
  -d "{\"version\": \"$1\"}"
