#!/bin/bash

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

###### USERS INPUT ############################################################

# Define image names
Source_image_name="HM12_2_4"
Image_name="HM12_2_4_thr120_conn"

# Image directory location ($PWD if current directory)
dir="$repo_root/images/raw"

# Choose image format
format='raw'

# Choose if the image is compressed or not
compressed='yes'

# Define image dimensions
x_dim=2000
y_dim=2000
z_dim=10

# Values of solid and pore in the thresholded raw image
pores_value=255
solid_value=0

# Enter pore index manually for STL mode only
pore_index_X=0
pore_index_Y=0
pore_index_Z=0

# resolution (m)
res=0.00003

# Define cropping parameters
x_min=700
x_max=1300
y_min=700
y_max=1300
z_min=1
z_max=2

# number of cells of initial mesh
# n*(nlevel+1) should be equal to image dimension when not binning 
n_x=600
n_y=600
#In 2D images, z has to be the empty direction
n_z=1

# flow direction 0 or 1, 2 is empty
direction=0

# Number of processors
NP=16

#### END OF USER INPUT #######################################################

# Load user environment variables 
source ~/.bashrc

MPIRUN=mpirun 

if [ $format != 'raw' ] && [ $format != 'stl' ]
then
        echo "ERROR: only raw and stl format are implemented for this solver"
        exit
fi

filename=$Image_name\.$format

if [ $compressed == 'yes' ]
then
        filename=$Image_name\.$format\.tar.gz
fi

if [ $format == 'raw' ]
then
    source_filename=$Source_image_name\.$format
    if [ $compressed == 'yes' ]
    then
        source_filename=$Source_image_name\.$format\.tar.gz
    fi
    cp $dir\/$source_filename constant/triSurface/.
else
    cp $dir\/$filename constant/triSurface/.
fi
cd constant/triSurface
if [ $compressed == 'yes' ]
then
        if [ $format == 'raw' ]
        then
            tar -xf $Source_image_name\.$format\.tar.gz
        else
            tar -xf $filename
        fi
fi

if [ $format == 'raw' ]
then
    python - <<'PY'
import numpy as np
from pathlib import Path
from collections import deque

src = Path("HM12_2_4.raw")
dst = Path("HM12_2_4_thr120.raw")
dst_conn = Path("HM12_2_4_thr120_conn.raw")
raw = np.fromfile(src, dtype=np.uint8)
binary = np.where(raw > 120, 255, 0).astype(np.uint8)
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

neighbors = (
    (-1, 0, 0),
    (1, 0, 0),
    (0, -1, 0),
    (0, 1, 0),
    (0, 0, -1),
    (0, 0, 1),
)

while queue:
    kz, jy, ix = queue.popleft()
    for dz, dy, dx in neighbors:
        nz = kz + dz
        ny = jy + dy
        nx = ix + dx
        if (
            0 <= nz < crop.shape[0]
            and 0 <= ny < crop.shape[1]
            and 0 <= nx < crop.shape[2]
            and not connected[nz, ny, nx]
            and crop[nz, ny, nx] == 255
        ):
            connected[nz, ny, nx] = True
            queue.append((nz, ny, nx))

crop_connected = np.where(connected, 255, 0).astype(np.uint8)
img[1:2, 700:1300, 700:1300] = crop_connected
img.reshape(-1).tofile(dst_conn)
print(
    f"Created {dst_conn.name} from {src.name} with threshold 120; "
    f"kept {int(connected.sum())} inlet-connected pore voxels in the crop"
)
PY
    echo -e "make stl"
    python raw2stl.py --x_min=$x_min --x_max=$x_max --y_min=$y_min --y_max=$y_max --z_min=$z_min --z_max=$z_max --pores_value=$pores_value --solid_value=$solid_value  --image_name=$Image_name --x_dim=$x_dim --y_dim=$y_dim --z_dim=$z_dim
    rm -f $Source_image_name.raw $Source_image_name.raw.tar.gz $Image_name.raw $Image_name.raw.tar.gz

    surfaceTransformPoints -translate '(-0.5 -0.5 -0.5)' Image_meshed.stl Image_meshed.stl > ../../surfaceTransformPoints.out
    vector="($res $res $res)"
    surfaceTransformPoints -scale "$vector" Image_meshed.stl Image_meshed.stl > ../../surfaceTransformPoints2.out
    pore_index_X="$(cat pore_indx)"
    pore_index_Y="$(cat pore_indy)"
    pore_index_Z="$(cat pore_indz)"

    pore_index_0=$(expr $pore_index_X*$res | bc)
    pore_index_1=$(expr $pore_index_Y*$res | bc)
    pore_index_2=$(expr $pore_index_Z*$res | bc)

elif [ $format == 'stl' ]
then
    echo -e "reading stl"
    mv $Image_name\.stl Image_meshed.stl
    rm -f $Image_name\.*
    tranX=$(expr -1*$x_min | bc)
    tranY=$(expr -1*$y_min | bc)
    tranZ=$(expr -1*$z_min | bc)
    vector="($tranX $tranY $tranZ)"
    surfaceTransformPoints -translate "$vector" Image_meshed.stl Image_meshed.stl > ../../surfaceTransformPoints1.out
    vector="($res $res $res)"
    surfaceTransformPoints -scale "$vector" Image_meshed.stl Image_meshed.stl > ../../surfaceTransformPoints2.out

    pore_index_0=$(expr $res*$pore_index_X-$res*$x_min | bc)
    pore_index_1=$(expr $res*$pore_index_Y-$res*$y_min | bc)
    pore_index_2=$(expr $res*$pore_index_Z-$res*$z_min | bc)
fi

echo -e "Coordinates at center of a pore = ($pore_index_0,$pore_index_1,$pore_index_2) in the cropped image"

cd ../..

echo -e "Create background mesh"
cp system/blockMeshDict2D$direction system/blockMeshDict
dx=$(expr $x_max-1*$x_min | bc)
dy=$(expr $y_max-1*$y_min | bc)
dz=$(expr $z_max-1*$z_min | bc)

sed -i "s/dx/$dx/g" system/blockMeshDict
sed -i "s/dy/$dy/g" system/blockMeshDict
sed -i "s/dz/$dz/g" system/blockMeshDict

sed -i "s/nx/$n_x/g" system/blockMeshDict
sed -i "s/ny/$n_y/g" system/blockMeshDict
sed -i "s/nz/$n_z/g" system/blockMeshDict

sed -i "s/res/$res/g" system/blockMeshDict

cp system/controlDictInit system/controlDict

blockMesh  > blockMesh.out

x_2=$(expr $dx*$res | bc)
y_2=$(expr $dy*$res | bc)
z_2=$(expr $dz*$res | bc)

x_1=0
y_1=0
z_1=0

cp system/postProcessDict1 system/postProcessDict
sed -i "s/x_1/$x_1/g" system/postProcessDict
sed -i "s/y_1/$y_1/g" system/postProcessDict
sed -i "s/z_1/$z_1/g" system/postProcessDict

sed -i "s/x_2/$x_2/g" system/postProcessDict
sed -i "s/y_2/$y_2/g" system/postProcessDict
sed -i "s/z_2/$z_2/g" system/postProcessDict

sed -i "s/flowdir/$direction/g" system/postProcessDict


cp system/postProcessDict1 system/postProcessDictRun
sed -i "s/x_1/$x_1/g" system/postProcessDictRun
sed -i "s/y_1/$y_1/g" system/postProcessDictRun
sed -i "s/z_1/$z_1/g" system/postProcessDictRun

sed -i "s/x_2/$x_2/g" system/postProcessDictRun
sed -i "s/y_2/$y_2/g" system/postProcessDictRun
sed -i "s/z_2/$z_2/g" system/postProcessDictRun

sed -i "s/flowdir/$direction/g" system/postProcessDictRun


cp system/snappyHexMeshDict2D system/snappyHexMeshDict

sed -i "s/poreIndex0/$pore_index_0/g" system/snappyHexMeshDict
sed -i "s/poreIndex1/$pore_index_1/g" system/snappyHexMeshDict
sed -i "s/poreIndex2/$pore_index_2/g" system/snappyHexMeshDict

if [ $NP -gt 1 ]
then
    cp system/decomposeParDict1 system/decomposeParDict
    sed -i "s/NP/$NP/g" system/decomposeParDict

    # Decompose background mesh
    echo -e "Decompose background mesh"
    decomposePar > decomposeBlockMesh.out

    rm -rf constant/polyMesh
fi

echo -e "BlockMesh and image created. Ready for snappyHexMesh" 
