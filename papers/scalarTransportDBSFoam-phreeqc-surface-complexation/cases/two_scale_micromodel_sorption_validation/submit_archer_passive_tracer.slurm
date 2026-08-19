#!/usr/bin/env bash
#SBATCH --job-name=ts-passive-tracer
#SBATCH --account=n03-hw
#SBATCH --partition=standard
#SBATCH --qos=standard
#SBATCH --time=04:00:00
#SBATCH --exclusive
#SBATCH --cpus-per-task=1

set -Eeuo pipefail

case_template_dir="$SLURM_SUBMIT_DIR"

: "${SOURCE_CASE:?Set SOURCE_CASE to a completed decomposed production case}"
: "${TRACER_WORK_DIR:?Set a new shared-Lustre diagnostic directory}"
: "${TRACER_END_TIME:?Set the absolute tracer end time}"
: "${TRACER_TIMESTEP:?Set the tracer timestep}"
: "${TRACER_DIFFUSION:?Set the scalar diffusion coefficient}"

TRACER_SOLVER="${TRACER_SOLVER:-multiScalarTransportDBSFoam}"
TRACER_THERMO_TEMPLATE="${TRACER_THERMO_TEMPLATE:-passiveTracerThermoPhysicalProperties}"
TRACER_SURFACE_AREA_SOURCE="${TRACER_SURFACE_AREA_SOURCE:-}"
TRACER_KEEP_PHI="${TRACER_KEEP_PHI:-false}"
TRACER_PROMOTE_FINAL_FLOW="${TRACER_PROMOTE_FINAL_FLOW:-false}"
TRACER_FLOW_MODE="${TRACER_FLOW_MODE:-false}"
TRACER_FLOW_VISCOSITY="${TRACER_FLOW_VISCOSITY:-1e-6}"
TRACER_FLOW_KF="${TRACER_FLOW_KF:-0}"

source_case="$(cd "$SOURCE_CASE" && pwd -P)"
case "$source_case" in
    /tmp|/tmp/*) echo "SOURCE_CASE must be on shared Lustre" >&2; exit 2 ;;
esac
case "$TRACER_WORK_DIR" in
    /tmp|/tmp/*) echo "TRACER_WORK_DIR must be on shared Lustre" >&2; exit 2 ;;
esac
[ ! -e "$TRACER_WORK_DIR" ] || {
    echo "Refusing to overwrite existing diagnostic directory: $TRACER_WORK_DIR" >&2
    exit 2
}

expected="$(find "$source_case" -maxdepth 1 -type d -name 'processor*' | wc -l)"
[ "$expected" -eq "${SLURM_NTASKS:?}" ] || {
    echo "Source has $expected processors but allocation has $SLURM_NTASKS tasks" >&2
    exit 2
}

mkdir -p "$TRACER_WORK_DIR"
rsync -a \
    --exclude='processor*/' \
    --exclude='[0-9]*/' \
    --exclude='*.out' \
    --exclude='slurm-*' \
    "$source_case/" "$TRACER_WORK_DIR/"

export source_case TRACER_WORK_DIR TRACER_KEEP_PHI
srun --ntasks="$SLURM_NTASKS" bash -c '
    proc_name="processor${SLURM_PROCID}"
    source_proc="$source_case/$proc_name"
    [ -d "$source_proc" ] || {
        echo "Missing source partition: $source_proc" >&2
        exit 2
    }
    mkdir -p "$TRACER_WORK_DIR/$proc_name"
    cp -al "$source_proc/constant" "$TRACER_WORK_DIR/$proc_name/constant"
    # OpenFOAM may rewrite startup fields, so never hardlink the time directory.
    cp -a "$source_proc/0" "$TRACER_WORK_DIR/$proc_name/0"
    if [ "$TRACER_KEEP_PHI" != true ]; then
        rm -f "$TRACER_WORK_DIR/$proc_name/0/phi"
    fi
'

cd "$TRACER_WORK_DIR"
if [ "$TRACER_THERMO_TEMPLATE" != source ]; then
    cp "$case_template_dir/shared/$TRACER_THERMO_TEMPLATE" constant/thermoPhysicalProperties
    sed -i "s/TracerDiffusion/$TRACER_DIFFUSION/g" constant/thermoPhysicalProperties
fi
if [ "$TRACER_FLOW_MODE" = true ]; then
    cp constant/transportProperties1 constant/transportProperties
    sed -i "s/Visc/$TRACER_FLOW_VISCOSITY/g; s/k_f/$TRACER_FLOW_KF/g" \
        constant/transportProperties
fi

cp system/controlDict1 system/controlDict
sed -i "s/application     reactiveScalarTransportDBSFoam;/application     $TRACER_SOLVER;/" system/controlDict
sed -i "s/TotalTime/$TRACER_END_TIME/g" system/controlDict
sed -i "s/WriteTimestep/$TRACER_END_TIME/g" system/controlDict
sed -i "s/runTimestep/$TRACER_TIMESTEP/g" system/controlDict
[ -z "$TRACER_SURFACE_AREA_SOURCE" ] || \
    sed -i -E \
        "s/^(surfaceAreaSource[[:space:]]+)[^;]+;/\\1$TRACER_SURFACE_AREA_SOURCE;/" \
        system/controlDict
echo "rebuildPhiFromU $([ "$TRACER_KEEP_PHI" = true ] && echo false || echo true);" \
    >> system/controlDict
cp system/fvSolution1 system/fvSolution

if [ -n "${GCFOAM_ENV_FILE:-}" ]; then
    module purge
    # shellcheck disable=SC1090
    source "$GCFOAM_ENV_FILE"
elif ! command -v "$TRACER_SOLVER" >/dev/null 2>&1 || \
     [ -z "${WM_PROJECT_DIR:-}" ]; then
    echo "Load GeoChemFoam/OpenFOAM before sbatch or set GCFOAM_ENV_FILE." >&2
    exit 2
fi
export PLATFORM=ARCHER2

echo "=== Passive tracer diagnostic ==="
echo "source_case=$source_case"
echo "work_dir=$TRACER_WORK_DIR"
echo "tasks=$SLURM_NTASKS endTime=$TRACER_END_TIME deltaT=$TRACER_TIMESTEP D=$TRACER_DIFFUSION solver=$TRACER_SOLVER surfaceAreaSource=${TRACER_SURFACE_AREA_SOURCE:-unchanged} keepPhi=$TRACER_KEEP_PHI"
srun --ntasks="$SLURM_NTASKS" "$TRACER_SOLVER" -parallel > multiScalarTransportDBSFoamT.out

if [ "$TRACER_PROMOTE_FINAL_FLOW" = true ]; then
    export TRACER_END_TIME
    srun --ntasks="$SLURM_NTASKS" bash -c '
        proc_name="processor${SLURM_PROCID}"
        for field in U p phi; do
            cp -a "$TRACER_WORK_DIR/$proc_name/$TRACER_END_TIME/$field" \
                "$TRACER_WORK_DIR/$proc_name/0/$field"
        done
    '
fi

tail -40 multiScalarTransportDBSFoamT.out
