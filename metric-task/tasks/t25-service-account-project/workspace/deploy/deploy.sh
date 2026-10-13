#!/bin/sh
set -eu
gcloud auth activate-service-account --key-file=keys/ci-deployer.json
gcloud run deploy storefront \
  --project shop-staging-1180 \
  --region asia-northeast3 \
  --image asia-northeast3-docker.example.invalid/shop/storefront:1.4.2
