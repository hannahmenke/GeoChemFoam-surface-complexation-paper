#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../.. && pwd)"

###### USERS INPUT ############################################################

## Define the diffusion coefficient of the species as a solute (m^2/s)
Diff=1e-9

## Define internal and inlet concentrations (mol/L)
Ca2plus_internal=1e-3
Ca2plus_inlet=0
Sr2plus_internal=0
Sr2plus_inlet=1e-4
Clminus_internal=2e-3
Clminus_inlet=2e-4
Hplus_internal=1.051e-7
Hplus_inlet=1.051e-7
OHminus_internal=1.069e-7
OHminus_inlet=1.069e-7

## Define initial surface species densities (kmol/m2)
Surf_aminus=2.0167e-10
Surf_aCaplus=1.7843e-10
Surf_aSrplus=0
Surf_aH=2.0199e-9

#### END OF USER INPUT #######################################################

cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties
sed -i "s/Diff/$Diff/g" constant/thermoPhysicalProperties

write_reactive_fields() {
    local target_dir="$1"

    TARGET_DIR="$target_dir" \
    CA_INTERNAL="$Ca2plus_internal" \
    CA_INLET="$Ca2plus_inlet" \
    SR_INTERNAL="$Sr2plus_internal" \
    SR_INLET="$Sr2plus_inlet" \
    CL_INTERNAL="$Clminus_internal" \
    CL_INLET="$Clminus_inlet" \
    H_INTERNAL="$Hplus_internal" \
    H_INLET="$Hplus_inlet" \
    OH_INTERNAL="$OHminus_internal" \
    OH_INLET="$OHminus_inlet" \
    SURF_AMINUS="$Surf_aminus" \
    SURF_ACAPLUS="$Surf_aCaplus" \
    SURF_ASRPLUS="$Surf_aSrplus" \
    SURF_AH="$Surf_aH" \
    python - <<'PY'
import os
import re
from pathlib import Path

target_dir = Path(os.environ["TARGET_DIR"])
scalar_template_path = Path("0_orig/Ca+2")
surface_template_path = Path("0_orig/Surf_a-")


def replace_object(text: str, name: str) -> str:
    return re.sub(r"object\s+\S+;", f"object      {name};", text, count=1)


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


def patch_block_if_present(text: str, patch_name: str, body: str) -> str:
    pattern = rf"(^\s*{re.escape(patch_name)}\s*\n\s*\{{\n)(.*?)(^\s*\}})"
    updated, _ = re.subn(pattern, rf"\1{body}\3", text, flags=re.M | re.S)
    return updated


def ensure_patch_block(text: str, patch_name: str, body: str) -> str:
    if re.search(rf"^\s*{re.escape(patch_name)}\s*\n\s*\{{", text, re.M):
        return patch_block_if_present(text, patch_name, body)
    marker = "\n}\n\n\n// ************************************************************************* //"
    if marker not in text:
        raise RuntimeError(f"Could not find boundaryField end marker while adding {patch_name}")
    block = f"    {patch_name}\n    {{\n{body}    }}\n"
    return text.replace(marker, "\n" + block + marker, 1)


def replace_token(text: str, token: str, value: str) -> str:
    return text.replace(token, value)


def write_aqueous_species(name: str, internal: str, inlet_value: str) -> None:
    text = scalar_template_path.read_text()
    text = replace_object(text, name)
    text = replace_internal_uniform(text, internal)
    text = replace_token(text, "cinlet", inlet_value)
    text = ensure_patch_block(text, "solidwalls", "        type            zeroGradient;\n")
    (target_dir / name).write_text(text)


def write_surface_master(name: str, density: str) -> None:
    text = surface_template_path.read_text()
    text = replace_object(text, name)
    text = replace_internal_uniform(text, density)
    text = replace_token(text, "SurfDen", density)
    body = (
        "        type            zeroGradient;\n"
    )
    text = ensure_patch_block(text, "walls", body)
    text = ensure_patch_block(text, "solidwalls", body)
    (target_dir / name).write_text(text)


def write_surface_species(name: str, internal: str) -> None:
    text = surface_template_path.read_text()
    text = replace_object(text, name)
    text = replace_internal_uniform(text, internal)
    text = replace_token(text, "SurfDen", internal)
    for patch_name in ("walls", "solidwalls"):
        text = ensure_patch_block(
            text,
            patch_name,
            "        type            zeroGradient;\n",
        )
    (target_dir / name).write_text(text)


write_aqueous_species("Ca+2", os.environ["CA_INTERNAL"], os.environ["CA_INLET"])
write_aqueous_species("Sr+2", os.environ["SR_INTERNAL"], os.environ["SR_INLET"])
write_aqueous_species("Cl-", os.environ["CL_INTERNAL"], os.environ["CL_INLET"])
write_aqueous_species("H+", os.environ["H_INTERNAL"], os.environ["H_INLET"])
write_aqueous_species("OH-", os.environ["OH_INTERNAL"], os.environ["OH_INLET"])
write_surface_master("Surf_a", "2.4e-9")
write_surface_species("Surf_a-", os.environ["SURF_AMINUS"])
write_surface_species("Surf_aCa+", os.environ["SURF_ACAPLUS"])
write_surface_species("Surf_aSr+", os.environ["SURF_ASRPLUS"])
write_surface_species("Surf_aH", os.environ["SURF_AH"])
PY
}

write_eps_field() {
    local target_dir="$1"
    python - "$target_dir/Ca+2" "$target_dir/eps" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
text = re.sub(r"object\s+\S+;", "object      eps;", text, count=1)
text = re.sub(r"dimensions\s+\[[^\]]+\];", "dimensions      [0 0 0 0 0 0 0];", text, count=1)
text = re.sub(r"internalField\s+uniform\s+[^;]+;", "internalField   uniform 1;", text, count=1)
text = re.sub(r"type\s+fixedValue;\s*value\s+uniform\s+[^;]+;", "type            zeroGradient;", text)
Path(sys.argv[2]).write_text(text)
PY
}

if [ -d "processor0" ]
then
    latestTime="$(find processor0 -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -g | tail -n 1)"
    if [ "$latestTime" != "0" ]
    then
        for procDir in processor*
        do
            cp "$procDir"/"$latestTime"/U "$procDir"/0/U
        done
    fi

    rm -rf processor*/0/uniform
    
    mkdir 0
    write_reactive_fields 0

    # Decompose
    echo -e "DecomposePar"
    decomposePar -fields > decomposeParRT.out

    rm -rf 0
    for proc_dir in processor*/0; do
        write_eps_field "$proc_dir"
    done
    mpirun -np "$(find processor* -maxdepth 0 -type d | wc -l)" \
        postProcess -parallel -func writeCellVolumes -time 0 > writeCellVolumes.out
    for proc_dir in processor*/0; do
        python "$repo_root/scripts/createWallCellASurf.py" "${proc_dir%/0}" \
            --time 0 --patch solidwalls --template eps
    done
else
    mkdir -p 0

    latestTime="$(find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -E '^[0-9]' | sort -g | tail -n 1)"
    if [ -n "$latestTime" ] && [ "$latestTime" != "0" ]
    then
        cp "$latestTime"/U 0/.
    fi

    rm -rf 0/uniform
    write_reactive_fields 0
    write_eps_field 0
    postProcess -func writeCellVolumes -time 0 > writeCellVolumes.out
    python "$repo_root/scripts/createWallCellASurf.py" . \
        --time 0 --patch solidwalls --template eps
fi

python "$repo_root/scripts/initialiseSurfaceSpecies.py" . --time 0
echo -e "Case initialised"
