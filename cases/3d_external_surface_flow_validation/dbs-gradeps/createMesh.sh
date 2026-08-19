#!/usr/bin/env bash

set -Eeuo pipefail

Image_name="estaillades_external_crop_phase"
format="raw"
x_dim=128
y_dim=128
z_dim=128
segmentation="phases"
pores_value=1
solid_value=3
phases=(1,3)
micro_por=(1,0.0001)
x_min=0
x_max=128
y_min=0
y_max=128
z_min=0
z_max=128
padWidth=0
res=0.000004
n_x=128
n_y=128
n_z=128
localRefinement="false"
layer=0
nlevel=0
refineStokes=0
dimension="3D"
direction=0
NPX=2
NPY=2
NPZ=2

mkdir -p constant/polyMesh constant/triSurface 0
cp ../shared/${Image_name}.raw constant/triSurface/.

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

NP=$(echo "$NPX*$NPY*$NPZ" | bc)
rm -f system/NP* system/Nx1 system/Ny1 system/Nz1
echo "$NPX" > system/NPX
echo "$NPY" > system/NPY
echo "$NPZ" > system/NPZ
echo "$n_x" > system/Nx1
echo "$n_y" > system/Ny1
echo "$n_z" > system/Nz1

eps_min=0
cyclic="no"
pad_value=$pores_value

python "$GCFOAM_DIR/applications/utilities/pyTools/writeASurfReconstructionDict.py" \
  $x_dim $y_dim $z_dim \
  $x_min $x_max $y_min $y_max $z_min $z_max \
  $n_x $n_y $n_z \
  $res \
  $Image_name \
  $pores_value $solid_value $dimension \
  occupancyGaussian 1.5 "" "" false

if [ "$NP" -gt 1 ]; then
  if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
    srun python "$GCFOAM_DIR/applications/utilities/pyTools/createMesh.py" \
      $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
      $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ
    srun python "$GCFOAM_DIR/applications/utilities/pyTools/createImage.py" \
      $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
      $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value \
      $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ eps
  else
    mpirun -np "$NP" python "$GCFOAM_DIR/applications/utilities/pyTools/createMesh.py" \
      $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
      $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ
    mpirun -np "$NP" python "$GCFOAM_DIR/applications/utilities/pyTools/createImage.py" \
      $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
      $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value \
      $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ eps
  fi
else
  python "$GCFOAM_DIR/applications/utilities/pyTools/createMesh.py" \
    $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
    $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ
  python "$GCFOAM_DIR/applications/utilities/pyTools/createImage.py" \
    $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
    $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value \
    $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ eps
fi

echo "DBS mesh and eps field created."
