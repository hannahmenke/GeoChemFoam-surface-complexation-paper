#!/bin/bash

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

###### USERS INPUT ############################################################

#Define image names
Source_image_name="HM12_2_4"
Image_name="HM12_2_4_thr120_conn"

#Image directory location ($PWD if current directory)
dir="$repo_root/images/raw"

#Choose image format
format='raw'

#Choose if the image is compressed or not
compressed='yes'

# Define image dimensions
x_dim=2000
y_dim=2000
z_dim=10

#segmentation='grayscale'
#Values of solid, pore, and minimum porosity value for the solid phase (note: if the image contains solid voxels, this CANNOT be 0)
#pores_value=255
#solid_value=0
#eps_min=0.0001

segmentation='phases'
#Values of solid and pore
pores_value=255
solid_value=0

#define the labels of the phases
phases=(0,255)

#define the porosity of each phase, note that the porosity of the solid phase CANNOT be 0, default to 0.0001
micro_por=(0.0001,1)

# Define cropping parameters
x_min=700
x_max=1300
y_min=700
y_max=1300
z_min=1
z_max=2

#padding for inlet/outlet
#This adds voxels in the image directly
padWidth=0

# define resolution (m)
res=0.00003

# number of cells of initial mesh
## They need to be a factor of the number of voxels in the padded image
n_x=300
n_y=300
n_z=1

#Mesh refinement level
localRefinement='false'
#number of layers around interface
layer=0
nlevel=0
refineStokes=0

#dimension="3D"
dimension="2D"
# flow direction 0, 1 or 2 
direction=0

# Number of processors in each direction
NPX=4
NPY=2
NPZ=1

#### END OF USER INPUT #######################################################

if [ $format != 'raw' ]
then
        echo "ERROR: only raw format is implemented for this solver"
        exit
fi

if [[ "${dimension}" == "2D" ]]
then
  if [ $direction == 2 ]
  then
     echo "ERROR: direction cannot be 2 in 2D simulations"
     exit
  elif [ $n_z -gt 1 ]
  then
     echo "ERROR: n_z= $n_z must be 1 in 2D simulations"
     exit
  elif [ $NPZ -gt 1 ]
  then
     echo "EROR: NPZ must be 1 in 2D simulations"
     exit
  elif [ $localRefinement == 'true' ]
  then
     echo "ERROR: no dynamicmeshRef for 2D simulations"
     exit
  fi
fi

#Insert dimensions in postProcessDict
x_1=0
y_1=0
z_1=0

xSize=$(echo "$x_max - $x_min" | bc)
ySize=$(echo "$y_max - $y_min" | bc)
zSize=$(echo "$z_max - $z_min" | bc)

x_2=$(expr $xSize*$res | bc)
y_2=$(expr $ySize*$res | bc)
z_2=$(expr $zSize*$res | bc)

cp system/postProcessDict1 system/postProcessDict
sed -i "s/x_1/$x_1/g" system/postProcessDict
sed -i "s/y_1/$y_1/g" system/postProcessDict
sed -i "s/z_1/$z_1/g" system/postProcessDict

sed -i "s/x_2/$x_2/g" system/postProcessDict
sed -i "s/y_2/$y_2/g" system/postProcessDict
sed -i "s/z_2/$z_2/g" system/postProcessDict

sed -i "s/flowdir/$direction/g" system/postProcessDict

mkdir -p constant/polyMesh

mkdir -p 0

filename=$Source_image_name\.$format

if [ $compressed == 'yes' ]
then
        filename=$Source_image_name\.$format\.tar.gz
fi

mkdir -p constant/triSurface
cp $dir\/$filename constant/triSurface/.
cd constant/triSurface
if [ $compressed == 'yes' ]
then
        tar -xf $filename
fi
python - <<'PY'
import numpy as np
from pathlib import Path
from collections import deque

src = Path("HM12_2_4.raw")
dst = Path("HM12_2_4_thr120.raw")
dst_conn = Path("HM12_2_4_thr120_conn.raw")
threshold = 120
raw = np.fromfile(src, dtype=np.uint8)
binary = np.where(raw > threshold, 255, 0).astype(np.uint8)
binary.tofile(dst)

img = binary.reshape((10, 2000, 2000))
crop = img[1:2, 700:1300, 700:1300]
connected = np.zeros_like(crop, dtype=bool)
queue = deque()
for kz in range(crop.shape[0]):
    for jy in range(crop.shape[1]):
        if crop[kz, jy, 0] == 255:
            connected[kz, jy, 0] = True
            queue.append((kz, jy, 0))
neighbors = ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1))
while queue:
    kz, jy, ix = queue.popleft()
    for dz, dy, dx in neighbors:
        nz, ny, nx = kz + dz, jy + dy, ix + dx
        if (
            0 <= nz < crop.shape[0]
            and 0 <= ny < crop.shape[1]
            and 0 <= nx < crop.shape[2]
            and not connected[nz, ny, nx]
            and crop[nz, ny, nx] == 255
        ):
            connected[nz, ny, nx] = True
            queue.append((nz, ny, nx))
img[1:2, 700:1300, 700:1300] = np.where(connected, 255, 0).astype(np.uint8)
img.reshape(-1).tofile(dst_conn)
print(
    f"Created {dst_conn.name} from {src.name} with threshold {threshold}; "
    f"kept {int(connected.sum())} inlet-connected pore voxels in the crop"
)
PY
cd ../..

NP=$(echo "$NPX*$NPY*$NPZ" | bc)

rm -f system/NP*

echo $NPX >> system/NPX
echo $NPY >> system/NPY
echo $NPZ >> system/NPZ

if [ $segmentation == 'grayscale' ]
then
	micro_por=0
	phases=0
elif [ $segmentation == 'phases' ]
then
    eps_min=0
fi

cyclic='no'
pad_value=$pores_value

if [[ $NP > 1 ]]; then
    # if PLATFORM is ARCHER2 then use srun, otherwise use serial version
    if [[ "${PLATFORM}" == "ARCHER2" ]]; then

        # error check that number of process files matches number of MPI tasks in parallel job
        if [[ ${NP} != ${SLURM_NTASKS} ]]
        then
           echo "ERROR: Number of MPI tasks does not equal number of processor files"
           exit
        fi

        # prepend spindle to srun command to pre-load python modules, otherwise comment-out sprindle line to simply use srun
       srun python $GCFOAM_DIR/applications/utilities/pyTools/createMesh.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ

       srun python $GCFOAM_DIR/applications/utilities/pyTools/createImage.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ 'eps'


    else
       mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createMesh.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ

       mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createImage.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ 'eps'

    fi
else
       python $GCFOAM_DIR/applications/utilities/pyTools/createMesh.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ

       python $GCFOAM_DIR/applications/utilities/pyTools/createImage.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ 'eps'


fi

if [ $localRefinement == 'true' ]
then
    echo -e "create topoSetDict"
    python $GCFOAM_DIR/applications/utilities/pyTools/createTopoSet.py $segmentation $eps_min $micro_por $refineStokes
    echo -e "refine mesh"

    cp system/fvSolution1 system/fvSolution
    sed -i "s/nSmooth/1/g" system/fvSolution
    sed -i "s/cSmooth/1/g" system/fvSolution

    for ((i=1; i < nlevel+1; i++))
    do
        if [[ $NP > 1 ]]; then
            # if PLATFORM is ARCHER2 then use srun, otherwise use serial version
            if [[ "${PLATFORM}" == "ARCHER2" ]]; then

                # error check that number of process files matches number of MPI tasks in parallel job
                if [[ ${NP} != ${SLURM_NTASKS} ]]
                then
                   echo "ERROR: Number of MPI tasks does not equal number of processor files"
                   exit
                fi

                for ((j=0; j < layer-1; j++))
                do
                  echo -e "smooth solid surface"
                  srun smoothSolidSurface -parallel > smoothSolidSurface.out
                done

                echo -e "refine fluid/solid interface"
                srun topoSet -parallel > topoSet.out
                srun refineHexMesh refinementRegion -overwrite -parallel > refineHexMesh.out

                echo -e "processMeshCellCenters"
                srun processMeshCellCenters -parallel > processMeshCellCenters.out

                echo "create refined eps"
                srun python $GCFOAM_DIR/applications/utilities/pyTools/createEpsRefinement.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $i $refineStokes $NPX $NPY $NPZ

            else
                for ((j=0; j < layer-1; j++))
                do
                    echo -e "smooth solid surface"
                    mpirun -np $NP smoothSolidSurface -parallel > smoothSolidSurface.out
                done

                echo -e "refine fluid/solid interface"
                mpirun -np $NP topoSet -parallel > topoSet.out
                mpirun -np $NP refineHexMesh refinementRegion -overwrite -parallel > refineHexMesh.out

                echo -e "processMeshCellCenters"
                mpirun -np $NP processMeshCellCenters -parallel > processMeshCellCenters.out

                echo "create refined eps"
                mpirun -np $NP python $GCFOAM_DIR/applications/utilities/pyTools/createImageRefinement.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $i $refineStokes $NPX $NPY $NPZ 'eps'

            fi

            rm -rf processor*/0/cellCenters
        else
            for ((j=0; j < layer-1; j++))
            do
                echo -e "smooth solid surface"
                smoothSolidSurface > smoothSolidSurface.out
            done

            echo -e "refine fluid/solid interface"
            topoSet > topoSet.out
            refineHexMesh refinementRegion -overwrite > refineHexMesh.out

            echo -e "processMeshCellCenters"
            processMeshCellCenters > processMeshCellCenters.out

            echo "create refined eps"
            python $GCFOAM_DIR/applications/utilities/pyTools/createImageRefinement.py $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $i $refineStokes $NPX $NPY $NPZ 'eps'

            rm -rf 0/cellCenters
        fi
    done
fi

rm -rf constant/triSurface

echo -e "Mesh created. It is advised to check in paraview to confirm mesh and 0/eps are reasonable before running flow"
