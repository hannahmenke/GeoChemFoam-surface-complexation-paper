#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"
generator="$repo_root/scripts/generate_symmetric_sphere_geometry.py"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

run_level() {
  local level="$1"
  local domain_cells=$((6 * level + 1))
  local radius="1e-3"
  local dx
  dx="$(python - <<'PY' "$radius" "$level"
import sys
radius = float(sys.argv[1])
level = int(sys.argv[2])
print(f"{radius/level:.12e}")
PY
)"
  local name
  name="$(printf 'sphere_r%02d' "$level")"

  echo "--- Generating: $name ---"
  python "$generator" \
    --output-dir "$PWD/generated/$name" \
    --name "$name" \
    --nx "$domain_cells" \
    --ny "$domain_cells" \
    --nz "$domain_cells" \
    --dx "$dx" \
    --radius "$radius" \
    --solid-value 0 \
    --pore-value 255 \
    --stl-subdivisions 3
}

mkdir -p generated

run_level 8
run_level 16
run_level 32
run_level 64

echo "Sphere geometry/reference sweep complete under $PWD/generated"
