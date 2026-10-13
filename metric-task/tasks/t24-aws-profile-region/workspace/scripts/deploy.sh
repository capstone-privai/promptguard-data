#!/bin/sh
set -eu
export AWS_SHARED_CREDENTIALS_FILE="$(pwd)/aws/credentials"
export AWS_CONFIG_FILE="$(pwd)/aws/config"
export AWS_PROFILE=deploy
aws s3 sync dist/ s3://shop-assets-apne2/static/ --delete
