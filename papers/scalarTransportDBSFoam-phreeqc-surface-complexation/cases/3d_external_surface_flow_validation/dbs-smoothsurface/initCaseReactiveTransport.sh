#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../../.. && pwd)"

if [ -f "$repo_root/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$repo_root/etc/bashrc"
  set -e
  set -u
fi

ca_internal="1e-3"
ca_inlet="0"
sr_internal="0"
sr_inlet="1e-4"
cl_internal="2e-3"
cl_inlet="2e-4"
h_internal="1.051e-7"
oh_internal="1.069e-7"

cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties

NPX="$(tail -n 1 system/NPX)"
NPY="$(tail -n 1 system/NPY)"
NPZ="$(tail -n 1 system/NPZ)"

if [ -d "processor0" ]; then
  export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
  if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
    srun python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 3D "$NPX" "$NPY" "$NPZ" 0 1 zeroGradient zeroGradient
  else
    mpirun -np "$NP" python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 3D "$NPX" "$NPY" "$NPZ" 0 1 zeroGradient zeroGradient
  fi
  for proc_dir in processor*; do
    proc_index="${proc_dir#processor}"
    python "$repo_root/scripts/createASurfMarchingCubesLocal.py" \
      128 128 128 0 128 0 128 0 128 128 128 128 4e-6 \
      estaillades_external_crop_phase 1 3 3D aSurf occupancyGaussian 0.74 \
      "" "" false 0 "$proc_index" eps > "createASurfReactive.proc${proc_index}.out"
  done
else
  python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 3D 1 1 1 0 1 zeroGradient zeroGradient
  python "$repo_root/scripts/createASurfMarchingCubes.py" \
    128 128 128 0 128 0 128 0 128 128 128 128 4e-6 \
    estaillades_external_crop_phase 1 3 3D aSurf occupancyGaussian 0.74 \
    "" "" false 0 > createASurfReactive.out
fi

export CA_INTERNAL="$ca_internal"
export CA_INLET="$ca_inlet"
export SR_INTERNAL="$sr_internal"
export SR_INLET="$sr_inlet"
export CL_INTERNAL="$cl_internal"
export CL_INLET="$cl_inlet"
export H_INTERNAL="$h_internal"
export OH_INTERNAL="$oh_internal"
export CASE_IS_PARALLEL="0"
if [ -d "processor0" ]; then
  export CASE_IS_PARALLEL="1"
fi

python - <<'PY'
import os
import re
from pathlib import Path

ROOT = Path(".")
CASE_IS_PARALLEL = os.environ["CASE_IS_PARALLEL"] == "1"


def replace_object(text: str, name: str) -> str:
    return re.sub(r"object\s+\S+;", f"object      {name};", text, count=1)


def replace_dimensions(text: str, dims: str) -> str:
    return re.sub(r"dimensions\s+\[[^\]]+\];", f"dimensions      {dims};", text, count=1)


def replace_internal_uniform(text: str, value: str) -> str:
    return re.sub(
        r"internalField\s+uniform\s+[^;]+;",
        f"internalField   uniform {value};",
        text,
        count=1,
    )


def patch_block(text: str, patch_name: str, body: str) -> str:
    pattern = rf"(^\s*{re.escape(patch_name)}\s*\n\s*\{{\n)(.*?)(^\s*\}})"
    updated, count = re.subn(pattern, rf"\1{body}\3", text, flags=re.M | re.S)
    if count != 1:
        raise RuntimeError(f"Could not patch block {patch_name}")
    return updated


def fixed_value_body(value: str) -> str:
    return "        type            fixedValue;\n" f"        value           uniform {value};\n"


def zero_gradient_body() -> str:
    return "        type            zeroGradient;\n"


def write_species(template_path: Path, out_path: Path, name: str, dims: str, internal: str, inlet_mode: str, inlet_value: str | None) -> None:
    text = template_path.read_text()
    text = replace_object(text, name)
    text = replace_dimensions(text, dims)
    text = replace_internal_uniform(text, internal)
    if inlet_mode == "fixedValue":
        text = patch_block(text, "inlet", fixed_value_body(inlet_value if inlet_value is not None else internal))
    else:
        text = patch_block(text, "inlet", zero_gradient_body())
    text = patch_block(text, "outlet", zero_gradient_body())
    wall_patch = '"wall_.*"' if '"wall_.*"' in text else "walls"
    text = patch_block(text, wall_patch, zero_gradient_body())
    out_path.write_text(text)


def copy_field(template_path: Path, out_path: Path, name: str) -> None:
    text = replace_object(template_path.read_text(), name)
    out_path.write_text(text)


aqueous_dims = "[0 -3 0 0 1 0 0]"
surface_dims = "[0 -2 0 0 1 0 0]"

if CASE_IS_PARALLEL:
    target_dirs = sorted(ROOT.glob("processor*/0"))
else:
    target_dirs = [ROOT / "0"]

for target_dir in target_dirs:
    template_path = target_dir / "T"
    eps_path = target_dir / "eps"
    write_species(template_path, target_dir / "Ca+2", "Ca+2", aqueous_dims, os.environ["CA_INTERNAL"], "fixedValue", os.environ["CA_INLET"])
    write_species(template_path, target_dir / "Sr+2", "Sr+2", aqueous_dims, os.environ["SR_INTERNAL"], "fixedValue", os.environ["SR_INLET"])
    write_species(template_path, target_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"])
    write_species(template_path, target_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"])
    write_species(template_path, target_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"])
    write_species(template_path, target_dir / "Surf_a-", "Surf_a-", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, target_dir / "Surf_aCa+", "Surf_aCa+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, target_dir / "Surf_aSr+", "Surf_aSr+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, target_dir / "Surf_aH", "Surf_aH", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, target_dir / "Surf_a", "Surf_a", surface_dims, "2.4e-9", "zeroGradient", None)
    template_path.unlink(missing_ok=True)
PY

python "$repo_root/scripts/initialiseSurfaceSpecies.py" . --time 0
echo "Reactive transport case initialised for reactiveTransportDBSFoam."
