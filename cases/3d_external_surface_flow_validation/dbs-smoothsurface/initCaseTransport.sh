#!/bin/bash

###### USERS INPUT ############################################################

#Initial tracer for species A and B (dimensionless)
A0=0.0
Ain=1.0
B0=0.0
Bin=0.0

#wall boundary type for transported species
wall_boundary_type="zeroGradient"

#Diffusion coefficients (m^2/s)
DiffA=1e-9
DiffB=1e-9

#model='molDiff' ##Deff=Diff

model='tortuosity'
## D=Diff/tau

#model='PecletDependent' 
## Dipsersivity constant
## Pe<1
## Dx=Diff/tau*(1+betax*Pe^alpha1x)
## Dy=Diff/tau*(1+betay*Pe^alpha1y)
## Dz=Diff/tau*(1+betaz*Pe^alpha1z)
## Pe>1
## Dx=Diff/tau*(1+betax**Pe^alpha2x)
## Dy=Diff/tau*(1+betay*Pe^alpha2y)
## Dz=Diff/tau*(1+betaz*Pe^alpha2z)


#define the labels of the phases
phases=(0,1)

#define the porosity of each phase, note that the porosity of the solid phase CANNOT be 0, default to 0.0001
micro_por=(0.0001,1)

##tortuosity factor of the solid/pore phases
tau=(2.5,1)

##micro pore size (m) - Pe = UL/Diff/eps
#Lpore=(5e-6,5e-6,5e-6)

#betax=(0.5,0.5,0)
#alpha1x=(1,1,1)
#alpha2x=(1,1,1)
#betay=(0.5,0.5,0)
#alpha1y=(1,1,1)
#alpha2y=(1,1,1)
#betaz=(0.5,0.5,0)
#alpha1z=(1,1,1)
#alpha2z=(1,1,1)

#### END OF USER INPUT

echo -e "set flow and transport properties"
cp constant/transportProperties2 constant/transportProperties
sed -i "s/Diff/$DiffA/g" constant/transportProperties

cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties
sed -i "s/DiffA/$DiffA/g" constant/thermoPhysicalProperties
sed -i "s/DiffB/$DiffB/g" constant/thermoPhysicalProperties

NPX="$(tail -n 1 system/NPX)"
NPY="$(tail -n 1 system/NPY)"
NPZ="$(tail -n 1 system/NPZ)"

if { [ -f 0/eps ] && grep -q "frontAndBack" 0/eps; } || \
   { [ -f processor0/0/eps ] && grep -q "frontAndBack" processor0/0/eps; }; then
   dimension="2D"
else dimension="3D"

fi

rename_scalar_field() {
    local file_path="$1"
    local field_name="$2"

    sed -i "s/object      T;/object      $field_name;/" "$file_path"
}

set_inlet_value() {
    local file_path="$1"
    local old_value="$2"
    local new_value="$3"

    sed -i "0,/value           uniform $old_value;/{s/value           uniform $old_value;/value           uniform $new_value;/}" "$file_path"
}

set_internal_value() {
    local file_path="$1"
    local old_value="$2"
    local new_value="$3"

    sed -i "s/internalField   uniform $old_value;/internalField   uniform $new_value;/" "$file_path"
}

copy_porosity_fields() {
    local eps_file="$1"
    local target_dir="$2"

    cp "$eps_file" "$target_dir"/epsNum
    cp "$eps_file" "$target_dir"/theta
    sed -i 's/object      eps;/object      epsNum;/' "$target_dir"/epsNum
    sed -i 's/object      eps;/object      theta;/' "$target_dir"/theta
}

create_species_fields() {
    local target_dir="$1"

    cp "$target_dir"/T "$target_dir"/A
    cp "$target_dir"/T "$target_dir"/B
    cp "$target_dir"/T "$target_dir"/Ydefault

    rename_scalar_field "$target_dir"/A A
    rename_scalar_field "$target_dir"/B B
    rename_scalar_field "$target_dir"/Ydefault Ydefault

    set_inlet_value "$target_dir"/A "$Ain" "$Ain"
    set_internal_value "$target_dir"/A "$A0" "$A0"
    set_inlet_value "$target_dir"/B "$Ain" "$Bin"
    set_internal_value "$target_dir"/B "$A0" "$B0"
    set_inlet_value "$target_dir"/Ydefault "$Ain" "$B0"
    set_internal_value "$target_dir"/Ydefault "$A0" "$B0"

    rm -f "$target_dir"/T
}

echo -e "create scalar template field"
if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"

    # if PLATFORM is ARCHER2 then use srun, otherwise use serial version
    if [[ "${PLATFORM}" == "ARCHER2" ]]; then
        srun python $GCFOAM_DIR/applications/utilities/pyTools/createT.py $dimension $NPX $NPY $NPZ $A0 $Ain $wall_boundary_type "zeroGradient"

	if [[ "$model" == "PecletDependent" ]];then
          echo "Calculate micro dispersivity"
          srun python $GCFOAM_DIR/applications/utilities/pyTools/createDeffPeDependent.py $dimension $DiffA $micro_por $tau $Lpore $betax $alpha1x $alpha2x  $betay $alpha1y $alpha2y $betaz $alpha1z $alpha2z $NPX $NPY $NPZ
	elif [[ "$model" == "tortuosity" ]];then
          echo "Calculate micro dispersivity"
          srun python $GCFOAM_DIR/applications/utilities/pyTools/createDefftort.py $dimension $DiffA $micro_por $tau $NPX $NPY $NPZ
	fi
    else
        mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createT.py $dimension $NPX $NPY $NPZ $A0 $Ain $wall_boundary_type "zeroGradient"

        if [[ "$model" == "PecletDependent" ]];then
          echo "Calculate micro dispersivity"
          mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createDeffPeDependent.py $dimension $DiffA $micro_por $tau $Lpore $betax $alpha1x $alpha2x  $betay $alpha1y $alpha2y $betaz $alpha1z $alpha2z $NPX $NPY $NPZ 
        elif [[ "$model" == "tortuosity" ]];then
          echo "Calculate micro dispersivity"
          mpirun -np $NP  python $GCFOAM_DIR/applications/utilities/pyTools/createDefftort.py $dimension $DiffA $micro_por $tau $NPX $NPY $NPZ
	fi
    fi

    for procDir in processor*
    do
        create_species_fields "$procDir"/0
        copy_porosity_fields "$procDir"/0/eps "$procDir"/0
    done
else
    python $GCFOAM_DIR/applications/utilities/pyTools/createT.py $dimension $NPX $NPY $NPZ $A0 $Ain $wall_boundary_type "zeroGradient"

    if [[ "$model" == "PecletDependent" ]];then
      echo "Calculate micro dispersivity"
      python $GCFOAM_DIR/applications/utilities/pyTools/createDeffPeDependent.py $dimension $DiffA $micro_por $tau $Lpore $betax $alpha1x $alpha2x  $betay $alpha1y $alpha2y $betaz $alpha1z $alpha2z $NPX $NPY $NPZ
    elif [[ "$model" == "tortuosity" ]];then
      echo "Calculate micro dispersivity"
      python $GCFOAM_DIR/applications/utilities/pyTools/createDefftort.py $dimension $DiffA $micro_por $tau $NPX $NPY $NPZ
    fi

    create_species_fields 0
    copy_porosity_fields 0/eps 0
fi

echo -e "Case initialised"
