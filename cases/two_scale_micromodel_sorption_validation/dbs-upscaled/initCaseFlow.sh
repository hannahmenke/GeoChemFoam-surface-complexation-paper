#!/bin/bash

###### USERS INPUT ############################################################

#Define boundary type
#boundary_type="flow_rate"
boundary_type="${BOUNDARY_TYPE:-pressure_drop}"
#Enter value (m^3/s) if boundary_type is flow_rate, velocity (m/s) if fixed_velocity, otherwise put 0
flowRate="${FLOW_RATE:-0}"
#Enter value (Pa) if boundary_type is pressure-drop, otherwise put 0 
pressureDrop="${PRESSURE_DROP:-7.60799581301e-05}"
#fluid kinematic viscosity (m2/s)
Visc=1e-6

model='phases'
matrix_properties="../results/matrix_rev_properties.json"
matrix_porosity="$(python - <<'PY' "$matrix_properties"
import json, sys
print(json.load(open(sys.argv[1]))["computed_from_matrix_rev"]["porosity"])
PY
)"
matrix_permeability="$(python - <<'PY' "$matrix_properties"
import json, sys
print(json.load(open(sys.argv[1]))["imported_transport_closure"]["permeability_m2"])
PY
)"

#define the labels of the phases
phases=(0,255)

#define the porosity of each phase, note that the porosity of the solid phase CANNOT be 0
micro_por=(1e-8,$matrix_porosity,1)

#define the permeability of each label (note: grain phase should be < 1e-20, pore should be > 1e6)
micro_k=(1e-16,$matrix_permeability,1e30)

#Kozeny-Carman constant
#kf=0

#### END OF USER INPUT #######################################################

if [[ $model == 'phases' ]];then
	kf=0
fi

echo "Boundary type: ${boundary_type} | flowRate: ${flowRate} | pressureDrop: ${pressureDrop}"
echo -e "set flow and transport properties"
cp constant/transportProperties1 constant/transportProperties
sed -i "s/Visc/$Visc/g" constant/transportProperties
sed -i "s/k_f/$kf/g" constant/transportProperties

NPX="$(tail -n 1 system/NPX)"
NPY="$(tail -n 1 system/NPY)"
NPZ="$(tail -n 1 system/NPZ)"

if { [ -f 0/eps ] && grep -q "frontAndBack" 0/eps; } || \
   { [ -f processor0/0/eps ] && grep -q "frontAndBack" processor0/0/eps; }; then
   dimension="2D"
else dimension="3D"

fi

echo -e "create U and p"
if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"

    # if PLATFORM is ARCHER2 then use srun, otherwise use serial version
    if [[ "${PLATFORM}" == "ARCHER2" ]]; then
        if [[ "$model" == "phases" ]];then
          echo "Calculate micro permeability"
          srun python $GCFOAM_DIR/applications/utilities/pyTools/createKinvPhases.py $dimension $micro_por $micro_k $NPX $NPY $NPZ
        fi

        srun python $GCFOAM_DIR/applications/utilities/pyTools/createU.py $dimension $NPX $NPY $NPZ $boundary_type $flowRate
        srun python $GCFOAM_DIR/applications/utilities/pyTools/createP.py $dimension $NPX $NPY $NPZ $boundary_type $pressureDrop

    else
        if [[ "$model" == "phases" ]];then
          echo "Calculate micro permeability"
          mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createKinvPhases.py $dimension $micro_por $micro_k $NPX $NPY $NPZ
        fi

        mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createU.py $dimension $NPX $NPY $NPZ $boundary_type $flowRate
        mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createP.py $dimension $NPX $NPY $NPZ $boundary_type $pressureDrop
    fi
else
    if [[ "$model" == "phases" ]];then
          echo "Calculate micro permeability"
          python $GCFOAM_DIR/applications/utilities/pyTools/createKinvPhases.py $dimension $micro_por $micro_k $NPX $NPY $NPZ
    fi

    python $GCFOAM_DIR/applications/utilities/pyTools/createU.py $dimension $NPX $NPY $NPZ $boundary_type $flowRate
    python $GCFOAM_DIR/applications/utilities/pyTools/createP.py $dimension $NPX $NPY $NPZ $boundary_type $pressureDrop
fi
