#!/bin/bash

set -e

###### USERS INPUT ############################################################

Diff=1e-9

Ca2plus=8.984e-4
Clminus=1.7968e-3
Hplus=1.051e-7
OHminus=1.069e-7

Surf_aminus=2.0167e-10
Surf_aCaplus=1.7843e-10
Surf_aH=2.0199e-9

#### END OF USER INPUT #######################################################

copy_closed_fields() {
    local target_dir="$1"

    cp 0_orig/U "$target_dir"/.
    cp 0_orig/p "$target_dir"/.
    cp 0_orig/Ca+2 "$target_dir"/.
    cp 0_orig/Cl- "$target_dir"/.
    cp 0_orig/H+ "$target_dir"/.
    cp 0_orig/OH- "$target_dir"/.
    cp 0_orig/Surf "$target_dir"/.
    cp 0_orig/Surf_a- "$target_dir"/.
    cp 0_orig/Surf_aCa+ "$target_dir"/.
    cp 0_orig/Surf_aH "$target_dir"/.

    sed -i "s/Ux/0/g" "$target_dir"/U
    sed -i "s/Uy/0/g" "$target_dir"/U
    sed -i "s/Uz/0/g" "$target_dir"/U

    sed -i "s/internalField   uniform 0;/internalField   uniform $Ca2plus;/" "$target_dir"/Ca+2
    sed -i "s/internalField   uniform 0;/internalField   uniform $Clminus;/" "$target_dir"/Cl-
    sed -i "s/internalField   uniform 0;/internalField   uniform $Hplus;/" "$target_dir"/H+
    sed -i "s/internalField   uniform 0;/internalField   uniform $OHminus;/" "$target_dir"/OH-

    sed -i "s/cinlet/$Ca2plus/g" "$target_dir"/Ca+2
    sed -i "s/cinlet/$Clminus/g" "$target_dir"/Cl-
    sed -i "s/cinlet/$Hplus/g" "$target_dir"/H+
    sed -i "s/cinlet/$OHminus/g" "$target_dir"/OH-

    sed -i "0,/type            fixedValue;/{s/type            fixedValue;/type            zeroGradient;/}" "$target_dir"/Ca+2
    sed -i "0,/type            fixedValue;/{s/type            fixedValue;/type            zeroGradient;/}" "$target_dir"/Cl-
    sed -i "0,/type            fixedValue;/{s/type            fixedValue;/type            zeroGradient;/}" "$target_dir"/H+
    sed -i "0,/type            fixedValue;/{s/type            fixedValue;/type            zeroGradient;/}" "$target_dir"/OH-

    sed -i "s/SurfDen/$Surf_aminus/g" "$target_dir"/Surf_a-
    sed -i "s/SurfDen/$Surf_aCaplus/g" "$target_dir"/Surf_aCa+
    sed -i "s/SurfDen/$Surf_aH/g" "$target_dir"/Surf_aH
}

cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties
sed -i "s/Diff/$Diff/g" constant/thermoPhysicalProperties

if [ -d "processor0" ]
then
    if [ ! -d "constant/polyMesh" ]
    then
        echo -e "reconstruct parallel mesh"
        reconstructParMesh -constant > reconstructParMeshClosed.out
    fi

    rm -rf processor*/0/uniform

    rm -rf 0
    mkdir 0
    copy_closed_fields 0

    echo -e "DecomposePar"
    decomposePar -fields > decomposeParRTClosed.out

    rm -rf 0
else
    rm -rf 0/uniform
    mkdir -p 0
    copy_closed_fields 0
fi

echo -e "Closed-system case initialised"
