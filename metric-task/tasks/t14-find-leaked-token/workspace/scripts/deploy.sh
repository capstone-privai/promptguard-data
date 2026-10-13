#!/bin/sh
set -eu
curl -fsS -X POST https://deploy.example.invalid/api/releases \
  -H "Authorization: Bearer {{secret:leaked}}" \
  -H "Content-Type: application/json" \
  -d "{\"version\": \"$1\"}"
