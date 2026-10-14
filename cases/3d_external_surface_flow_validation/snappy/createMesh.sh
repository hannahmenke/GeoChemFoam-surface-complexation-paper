#!/usr/bin/env bash

set -Eeuo pipefail

repo_root="$(cd "$(dirname "$0")"/../../.. && pwd)"

Image_name="estaillades_external_crop_binary"
format="raw"
x_dim=128
y_dim=128
z_dim=128
pores_value=255
solid_value=0
res=0.000004
x_min=0
x_max=128
y_min=0
y_max=128
z_min=0
z_max=128
n_x=128
n_y=128
n_z=128
n_level=0
direction=0
NP="${NPROCS:-8}"

mkdir -p constant/triSurface
cp ../shared/${Image_name}.raw constant/triSurface/.

cd constant/triSurface
echo "make stl"
python "$repo_root/scripts/raw2stl.py" \
  --x_min=$x_min --x_max=$x_max \
  --y_min=$y_min --y_max=$y_max \
  --z_min=$z_min --z_max=$z_max \
  --pores_value=$pores_value --solid_value=$solid_value \
  --image_name=$Image_name --x_dim=$x_dim --y_dim=$y_dim --z_dim=$z_dim
rm -f ${Image_name}.raw

surfaceTransformPoints -translate '(-0.5 -0.5 -0.5)' Image_meshed.stl Image_meshed.stl > ../../surfaceTransformPoints1.out
surfaceTransformPoints -scale "($res $res $res)" Image_meshed.stl Image_meshed.stl > ../../surfaceTransformPoints2.out
pore_index_X="$(cat pore_indx)"
pore_index_Y="$(cat pore_indy)"
pore_index_Z="$(cat pore_indz)"
pore_index_0=$(expr $pore_index_X*$res | bc)
pore_index_1=$(expr $pore_index_Y*$res | bc)
pore_index_2=$(expr $pore_index_Z*$res | bc)
cd ../..

echo "Coordinates at center of a pore = ($pore_index_0,$pore_index_1,$pore_index_2)"

echo "Create background mesh"
cp system/blockMeshDict${direction} system/blockMeshDict
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
blockMesh > blockMesh.out

x_1=0
y_1=0
z_1=0
x_2=$(expr $dx*$res | bc)
y_2=$(expr $dy*$res | bc)
z_2=$(expr $dz*$res | bc)

cp system/postProcessDict1 system/postProcessDict
sed -i "s/x_1/$x_1/g" system/postProcessDict
sed -i "s/y_1/$y_1/g" system/postProcessDict
sed -i "s/z_1/$z_1/g" system/postProcessDict
sed -i "s/x_2/$x_2/g" system/postProcessDict
sed -i "s/y_2/$y_2/g" system/postProcessDict
sed -i "s/z_2/$z_2/g" system/postProcessDict
sed -i "s/flowdir/$direction/g" system/postProcessDict

cp system/snappyHexMeshDict1 system/snappyHexMeshDict
sed -i "s/nlevel/$n_level/g" system/snappyHexMeshDict
sed -i "s/poreIndex0/$pore_index_0/g" system/snappyHexMeshDict
sed -i "s/poreIndex1/$pore_index_1/g" system/snappyHexMeshDict
sed -i "s/poreIndex2/$pore_index_2/g" system/snappyHexMeshDict

if [ "$NP" -gt 1 ]; then
  cp system/decomposeParDict1 system/decomposeParDict
  sed -i "s/NP/$NP/g" system/decomposeParDict
  echo "Decompose background mesh"
  decomposePar > decomposeBlockMesh.out
  rm -rf constant/polyMesh
fi

echo "blockMesh and STL image created. Ready for snappyHexMesh"
