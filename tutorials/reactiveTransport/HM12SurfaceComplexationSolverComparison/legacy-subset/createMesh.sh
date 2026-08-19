#!/bin/bash

set -euo pipefail

Source_image_name="HM12_2_4"
Image_name="HM12_2_4_thr120_conn"
dir="$GCFOAM_IMG/raw"
compressed='yes'

x_dim=2000
y_dim=2000
z_dim=10

pores_value=255
solid_value=0
segmentation='phases'
phases=(0,255)
micro_por=(0.0001,1)
eps_min=0

x_min=700
x_max=1300
y_min=700
y_max=1300
z_min=1
z_max=2

res=0.00003
n_x=600
n_y=600
n_z=1
dimension="2D"
direction=0
padWidth=0
pad_value=$pores_value
cyclic='no'
NP=16

source ~/.bashrc

mkdir -p constant/polyMesh constant/triSurface
rm -rf constant/polyMesh/*
rm -rf 0
mkdir -p 0

cp "$dir/$Source_image_name.raw.tar.gz" constant/triSurface/.
cd constant/triSurface
tar -xf "$Source_image_name.raw.tar.gz"
python - <<'PY2'
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
PY2
cd ../..

cp system/blockMeshDict2D0 system/blockMeshDict
dx=$(expr $x_max - $x_min | bc)
dy=$(expr $y_max - $y_min | bc)
dz=$(expr $z_max - $z_min | bc)
sed -i "s/dx/$dx/g" system/blockMeshDict
sed -i "s/dy/$dy/g" system/blockMeshDict
sed -i "s/dz/$dz/g" system/blockMeshDict
sed -i "s/nx/$n_x/g" system/blockMeshDict
sed -i "s/ny/$n_y/g" system/blockMeshDict
sed -i "s/nz/$n_z/g" system/blockMeshDict
sed -i "s/res/$res/g" system/blockMeshDict

cp system/controlDictInit system/controlDict
blockMesh > blockMesh.out

echo 1 > system/NPX
echo 1 > system/NPY
echo 1 > system/NPZ

python "$GCFOAM_DIR/applications/utilities/pyTools/createImage.py"     $x_dim $y_dim $z_dim     $x_min $x_max $y_min $y_max $z_min $z_max     $n_x $n_y $n_z $res     $Image_name $padWidth $pad_value     $pores_value $solid_value $eps_min     $dimension $direction $cyclic     $segmentation $micro_por $phases 1 1 1 'eps'

python - <<'PY2'
from pathlib import Path
path = Path("0/eps")
text = path.read_text()
text = text.replace('"wall_.*"', 'walls')
text = text.replace('frontAndBack', 'frontandback')
path.write_text(text)
PY2

cat > system/topoSetDict <<'EOF'
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      topoSetDict;
}

actions
(
    {
        name poreCells;
        type cellSet;
        action new;
        source fieldToCell;
        field eps;
        min 0.5;
        max 1.001;
    }
);
EOF

topoSet > topoSet.out
subsetMesh poreCells -overwrite > subsetMesh.out

python - <<'PY2'
from pathlib import Path
import re
boundary_path = Path("constant/polyMesh/boundary")
text = boundary_path.read_text()
if "oldInternalFaces" not in text:
    raise SystemExit("oldInternalFaces patch not found after subsetMesh")

text = text.replace("oldInternalFaces", "fixedWalls", 1)

def set_patch_type(src: str, patch_name: str, patch_type: str) -> str:
    pattern = r"(" + re.escape(patch_name) + r"\s*\{.*?type\s+)(\w+)(;.*?\})"
    repl = r"\g<1>" + patch_type + r"\g<3>"
    new, count = re.subn(pattern, repl, src, count=1, flags=re.S)
    if count != 1:
        raise SystemExit("Could not set patch type for " + patch_name)
    return new

text = set_patch_type(text, "walls", "wall")
text = set_patch_type(text, "inlet", "patch")
text = set_patch_type(text, "outlet", "patch")
text = set_patch_type(text, "frontandback", "empty")
text = set_patch_type(text, "fixedWalls", "wall")

boundary_path.write_text(text)

eps_path = Path("0/eps")
eps = eps_path.read_text()
eps = eps.replace("oldInternalFaces", "fixedWalls")
eps = eps.replace('"wall_.*"', 'walls')
eps = eps.replace('frontAndBack', 'frontandback')

def upsert_boundary_entry(src: str, patch_name: str, patch_body: str) -> str:
    patch_pattern = re.compile(
        r"(^\s*" + re.escape(patch_name) + r"\s*\n\s*\{.*?^\s*\})",
        re.M | re.S,
    )
    entry = patch_name + "\n    {\n" + patch_body + "\n    }"
    if patch_pattern.search(src):
        return patch_pattern.sub(entry, src, count=1)

    boundary_field_pattern = re.compile(r"(boundaryField\s*\{\n)(.*)(\n\})", re.S)
    match = boundary_field_pattern.search(src)
    if not match:
        raise SystemExit("Could not find boundaryField block in 0/eps")
    return (
        src[:match.start()]
        + match.group(1)
        + match.group(2)
        + "\n    "
        + entry.replace("\n", "\n    ")
        + match.group(3)
        + src[match.end():]
    )

eps = upsert_boundary_entry(
    eps,
    "fixedWalls",
    "        type            zeroGradient;",
)
eps_path.write_text(eps)
PY2

rm -rf processor*
renumberMesh -overwrite > renumberMesh.out

cp system/decomposeParDict1 system/decomposeParDict
sed -i "s/NP/$NP/g" system/decomposeParDict
decomposePar -force > decomposeParMesh.out

rm -rf 0 constant/triSurface

echo "Subset legacy mesh created. Ready for flow/reactive transport."
