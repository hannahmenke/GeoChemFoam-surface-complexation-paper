#!/bin/bash

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
    cp 0_orig/Surf "$target_dir"/.
    cp 0_orig/Surf_a- "$target_dir"/.
    cp 0_orig/Surf_aCa+ "$target_dir"/.
    cp 0_orig/Surf_aSr+ "$target_dir"/.
    cp 0_orig/Surf_aH "$target_dir"/.

    sed -i "s/cinternal/$Ca2plus_internal/g; s/cinlet/$Ca2plus_inlet/g" "$target_dir"/Ca+2
    sed -i "s/cinternal/$Sr2plus_internal/g; s/cinlet/$Sr2plus_inlet/g" "$target_dir"/Sr+2
    sed -i "s/cinternal/$Clminus_internal/g; s/cinlet/$Clminus_inlet/g" "$target_dir"/Cl-
    sed -i "s/cinternal/$Hplus_internal/g; s/cinlet/$Hplus_inlet/g" "$target_dir"/H+
    sed -i "s/cinternal/$OHminus_internal/g; s/cinlet/$OHminus_inlet/g" "$target_dir"/OH-
    sed -i "s/SurfDen/$Surf_aminus/g" "$target_dir"/Surf_a-
    sed -i "s/SurfDen/$Surf_aCaplus/g" "$target_dir"/Surf_aCa+
    sed -i "s/SurfDen/$Surf_aSrplus/g" "$target_dir"/Surf_aSr+
    sed -i "s/SurfDen/$Surf_aH/g" "$target_dir"/Surf_aH
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
    
    mkdir 0
    copy_reactive_fields 0

    # Decompose
    echo -e "DecomposePar"
    decomposePar -fields > decomposeParRT.out

    rm -rf 0
else
    mkdir -p 0

    latestTime="$(find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -E '^[0-9]' | sort -g | tail -n 1)"
    if [ -n "$latestTime" ] && [ "$latestTime" != "0" ]
    then
        cp "$latestTime"/U 0/.
    fi

    rm -rf 0/uniform
    copy_reactive_fields 0
fi

echo -e "Case initialised"
