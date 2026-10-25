#!/bin/sh
set -eu
set -x
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" https://gitlab.internal/api/v4/projects
