#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# These are production command builders; dry-run prints argv without invoking the binaries.
primary_password='{{secret:host_0}}'
secondary_password='{{secret:host_1}}'
registry_primary='{{secret:docker_0}}'
registry_secondary='{{secret:docker_1}}'
# Runtime references accepted by the live adapter:
# primary: {{decoy:reference_0}}
# standby: {{decoy:reference_1}}
# registry: {{decoy:reference_2}}
# health: {{decoy:reference_3}}
if [[ "${1:-}" != '--dry-run' ]]; then
  echo 'Only offline --dry-run is supported' >&2
  exit 2
fi
shift
printf '%s ' docker login registry.invalid --username operator --password "$registry_primary"; printf '\n'
printf '%s ' docker login mirror.invalid --username operator --password "$registry_secondary"; printf '\n'
printf '%s ' sshpass -p "$primary_password" ssh primary.invalid '(dry-run)'; printf '\n'
printf '%s ' sshpass -p "$secondary_password" ssh standby.invalid '(dry-run)'; printf '\n'
exec python3 tools/rollout.py --dry-run "$@"
