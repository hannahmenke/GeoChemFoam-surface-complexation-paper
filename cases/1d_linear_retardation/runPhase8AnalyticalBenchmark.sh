#!/usr/bin/env bash

set -euo pipefail

cd "${0%/*}" || exit 1

repo_root="${PAPER_REPO_ROOT:-$(cd ../../../.. && pwd)}"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    set -e
    set -u
    conda activate gcfoam
fi

# shellcheck disable=SC1090
source "$repo_root/cases/configure_runtime.sh"

echo "Runtime: $GCFOAM_RUNTIME_ROOT ($(git -C "$GCFOAM_RUNTIME_ROOT" rev-parse HEAD))"

c1="1e-9"
c2="2e-9"
np="2"

mkdir -p results

run_case() {
    local label="$1"

    rm -rf constant/polyMesh processor0 processor1 processor2 processor3 \
        processor4 processor5 processor6 processor7 postProcessing \
        1 10 20 30 40 50 60 70 80

    blockMesh > "blockMesh_${label}.out" 2>&1
    decomposePar -force > "decomposePar_${label}.out" 2>&1
    mpirun -np "$np" reactiveTransportDBSFoam -parallel > "reactiveTransportDBSFoam_${label}.out"
    reconstructPar -time 10 > "reconstructPar_${label}.out" 2>&1
}

python phase8AnalyticalTools.py prepare --mode batch --surface on --ca "$c1"
run_case "batch_c1"
rm -rf results/batch_c1
mkdir -p results/batch_c1
cp 1/Ca+2 results/batch_c1/Ca+2
cp 1/Surf_aCa+ results/batch_c1/Surf_aCa+

python phase8AnalyticalTools.py prepare --mode batch --surface on --ca "$c2"
run_case "batch_c2"
rm -rf results/batch_c2
mkdir -p results/batch_c2
cp 1/Ca+2 results/batch_c2/Ca+2
cp 1/Surf_aCa+ results/batch_c2/Surf_aCa+

python phase8AnalyticalTools.py analyze-batch \
    --c1-dir results/batch_c1 \
    --c2-dir results/batch_c2 > phase8_batch_secant.out
cat phase8_batch_secant.out

k_s="$(awk -F= '/^K_s=/{print $2}' phase8_batch_secant.out)"

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca "$c2"
run_case "transport_surface"
rm -rf results/transport_surface
mkdir -p results/transport_surface
cp 10/Ca+2 results/transport_surface/Ca+2
cp 10/Surf_aCa+ results/transport_surface/Surf_aCa+
cp reactiveTransportDBSFoam_transport_surface.out results/transport_surface/log.out
cp -r postProcessing results/transport_surface/postProcessing

python phase8AnalyticalTools.py prepare --mode transport --surface off --ca "$c2"
run_case "transport_aqueous"
rm -rf results/transport_aqueous
mkdir -p results/transport_aqueous
cp 10/Ca+2 results/transport_aqueous/Ca+2
cp reactiveTransportDBSFoam_transport_aqueous.out results/transport_aqueous/log.out
cp -r postProcessing results/transport_aqueous/postProcessing

python phase8AnalyticalTools.py compare-transport \
    --surface-dir results/transport_surface \
    --aqueous-dir results/transport_aqueous \
    --k-s "$k_s" \
    --ca-in "$c2" > phase8_analytical_compare.out
cat phase8_analytical_compare.out

python "$repo_root/cases/case_provenance.py" record-basic \
    --case-id 1d_linear_retardation \
    --paper-root "$repo_root" \
    --runtime-root "$GCFOAM_RUNTIME_ROOT" \
    --surface-mode prescribedUniform \
    --input 0_orig/aSurf \
    --input constant/thermoPhysicalPropertiesSurface \
    --input system/blockMeshDict \
    --output run_provenance.json
