#!/bin/sh
# nightly logical backup
set -eu
PGPASSWORD='{{secret:db_password_old}}' pg_dump -h shop-db.internal -U shop -Fc shop > "/backups/shop-$(date +%F).dump"
