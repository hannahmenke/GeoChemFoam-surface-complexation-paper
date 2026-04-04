#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"

exec "$repo_root/scripts/run_sphere_area_mesh_only_benchmark.sh" "$@"
