#!/bin/bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

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

copy_reactive_fields() {
    local target_dir="$1"

    cp 0_orig/Ca+2 "$target_dir"/.
    cp 0_orig/Sr+2 "$target_dir"/.
    cp 0_orig/Cl- "$target_dir"/.
    cp 0_orig/H+ "$target_dir"/.
    cp 0_orig/OH- "$target_dir"/.
    cp 0_orig/Surf_a- "$target_dir"/.
    cp 0_orig/Surf_aCa+ "$target_dir"/.
    cp 0_orig/Surf_aSr+ "$target_dir"/.
    cp 0_orig/Surf_aH "$target_dir"/.
    cp 0_orig/Surf_a "$target_dir"/.

    python - \
        "$target_dir/Ca+2" "$Ca2plus_internal" \
        "$target_dir/Sr+2" "$Sr2plus_internal" \
        "$target_dir/Cl-" "$Clminus_internal" \
        "$target_dir/H+" "$Hplus_internal" \
        "$target_dir/OH-" "$OHminus_internal" <<'PY'
import re
import sys
from pathlib import Path

arguments = sys.argv[1:]
for field_name, value in zip(arguments[0::2], arguments[1::2]):
    path = Path(field_name)
    text = path.read_text()
    updated, count = re.subn(
        r"internalField\s+uniform\s+[^;]+;",
        f"internalField   uniform {value};",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Expected one uniform internalField in {path}")
    path.write_text(updated)
PY

    sed -i "s/cinlet/$Ca2plus_inlet/g" "$target_dir"/Ca+2
    sed -i "s/cinlet/$Sr2plus_inlet/g" "$target_dir"/Sr+2
    sed -i "s/cinlet/$Clminus_inlet/g" "$target_dir"/Cl-
    sed -i "s/cinlet/$Hplus_inlet/g" "$target_dir"/H+
    sed -i "s/cinlet/$OHminus_inlet/g" "$target_dir"/OH-
    sed -i "s/SurfDen/$Surf_aminus/g" "$target_dir"/Surf_a-
    sed -i "s/SurfDen/$Surf_aCaplus/g" "$target_dir"/Surf_aCa+
    sed -i "s/SurfDen/$Surf_aSrplus/g" "$target_dir"/Surf_aSr+
    sed -i "s/SurfDen/$Surf_aH/g" "$target_dir"/Surf_aH
    sed -i "s/SurfDen/2.4e-9/g" "$target_dir"/Surf_a
}

write_eps_field() {
    local target_dir="$1"
    python - "$target_dir/Ca+2" "$target_dir/eps" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text()
source = re.sub(r"object\s+\S+;", "object      eps;", source, count=1)
source = re.sub(r"dimensions\s+\[[^\]]+\];", "dimensions      [0 0 0 0 0 0 0];", source, count=1)
source = re.sub(r"internalField\s+uniform\s+[^;]+;", "internalField   uniform 1;", source, count=1)
source = re.sub(r"type\s+fixedValue;\s*value\s+uniform\s+[^;]+;", "type            zeroGradient;", source)
Path(sys.argv[2]).write_text(source)
PY
}

cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties
sed -i "s/Diff/$Diff/g" constant/thermoPhysicalProperties

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
    
    rm -rf 0
    mkdir -p 0
    copy_reactive_fields 0

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
            --time 0 --patch fixedWalls --template eps
    done
else
    mkdir -p 0

    latestTime="$(find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -E '^[0-9]' | sort -g | tail -n 1)"
    if [ -n "$latestTime" ] && [ "$latestTime" != "0" ]
    then
        cp "$latestTime"/U 0/.
    fi

    rm -rf 0/uniform
    copy_reactive_fields 0
    write_eps_field 0
    postProcess -func writeCellVolumes -time 0 > writeCellVolumes.out
    python "$repo_root/scripts/createWallCellASurf.py" . \
        --time 0 --patch fixedWalls --template eps
fi

python "$repo_root/scripts/initialiseSurfaceSpecies.py" . --time 0
echo -e "Case initialised"
