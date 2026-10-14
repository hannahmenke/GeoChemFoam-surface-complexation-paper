#!/usr/bin/env bash

set -Eeuo pipefail

Image_name="resolved_full_reference"
format="raw"
metadata="../shared/metadata.json"
x_dim="$(python - <<'PY' "$metadata"
import json, sys
print(json.load(open(sys.argv[1]))["resolved_full_reference"]["shape"][0])
PY
)"
y_dim="$(python - <<'PY' "$metadata"
import json, sys
print(json.load(open(sys.argv[1]))["resolved_full_reference"]["shape"][1])
PY
)"
res="$(python - <<'PY' "$metadata"
import json, sys
print(json.load(open(sys.argv[1]))["resolved_full_reference"]["voxel_size_m"])
PY
)"
z_dim=1
segmentation="phases"
pores_value=255
solid_value=0
phases=(0,255)
micro_por=(1e-8,1)
x_min=0
x_max="$x_dim"
y_min=0
y_max="$y_dim"
z_min=0
z_max=1
padWidth=0
n_x="$x_dim"
n_y="$y_dim"
n_z=1
localRefinement="false"
dimension="2D"
direction=0
NPX="${RESOLVED_NPX:-${GCFOAM_NPX:-8}}"
NPY="${RESOLVED_NPY:-${GCFOAM_NPY:-4}}"
NPZ="${RESOLVED_NPZ:-${GCFOAM_NPZ:-1}}"

mkdir -p constant/polyMesh constant/triSurface 0
cp ../shared/${Image_name}.raw constant/triSurface/.

x_1=0
y_1=0
z_1=0
xSize=$((x_max - x_min))
ySize=$((y_max - y_min))
zSize=$((z_max - z_min))
x_2=$(awk -v n="$xSize" -v dx="$res" 'BEGIN {printf "%.12g", n * dx}')
y_2=$(awk -v n="$ySize" -v dx="$res" 'BEGIN {printf "%.12g", n * dx}')
z_2=$(awk -v n="$zSize" -v dx="$res" 'BEGIN {printf "%.12g", n * dx}')

cp system/postProcessDict1 system/postProcessDict
sed -i "s/x_1/$x_1/g" system/postProcessDict
sed -i "s/y_1/$y_1/g" system/postProcessDict
sed -i "s/z_1/$z_1/g" system/postProcessDict
sed -i "s/x_2/$x_2/g" system/postProcessDict
sed -i "s/y_2/$y_2/g" system/postProcessDict
sed -i "s/z_2/$z_2/g" system/postProcessDict
sed -i "s/flowdir/$direction/g" system/postProcessDict

NP=$(echo "$NPX*$NPY*$NPZ" | bc)
echo "$NPX" > system/NPX
echo "$NPY" > system/NPY
echo "$NPZ" > system/NPZ
echo "$n_x" > system/Nx1
echo "$n_y" > system/Ny1
echo "$n_z" > system/Nz1
printf '%s\n' "$res" > system/cellSize

eps_min=0
cyclic="no"
pad_value=$pores_value

if [ "$NP" -gt 1 ]; then
  if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
    parallel_run=(srun --ntasks="$NP")
  else
    parallel_run=(mpirun -np "$NP")
  fi
  "${parallel_run[@]}" python "$GCFOAM_DIR/applications/utilities/pyTools/createMesh.py" \
    $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
    $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ
  "${parallel_run[@]}" python "$GCFOAM_DIR/applications/utilities/pyTools/createImage.py" \
    $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
    $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value \
    $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ eps
else
  python "$GCFOAM_DIR/applications/utilities/pyTools/createMesh.py" \
    $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
    $n_x $n_y $n_z $res $padWidth $dimension $direction $cyclic $NPX $NPY $NPZ
  python "$GCFOAM_DIR/applications/utilities/pyTools/createImage.py" \
    $x_dim $y_dim $z_dim $x_min $x_max $y_min $y_max $z_min $z_max \
    $n_x $n_y $n_z $res $Image_name $padWidth $pad_value $pores_value $solid_value \
    $eps_min $dimension $direction $cyclic $segmentation $micro_por $phases $NPX $NPY $NPZ eps
fi

echo "Resolved reference mesh and eps field created."
