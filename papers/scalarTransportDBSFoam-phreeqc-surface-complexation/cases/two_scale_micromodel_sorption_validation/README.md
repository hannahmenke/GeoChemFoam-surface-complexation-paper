# Two-Scale Micromodel Sorption Validation

This benchmark compares Li-selective sorption from a Na-Mg brine in equal-size
resolved and DBS multiscale micromodel domains. The chemistry is a simplified
direct-lithium-extraction-style surface-complexation system: incoming Li
competes with Na, K, and Mg for a generic sorbent site. It is intended as a
surface-area-controlled sorption benchmark, not as a parameterization of a
specific commercial sorbent.

The `surfaceMasterDensities` value is in OpenFOAM's native kmol/m2 amount
unit: `2.4e-9 kmol/m2`, equivalent to the physical site density
`2.4e-6 mol/m2`. PhreeqcRM is configured for surface amounts per litre of
water. The benchmark keeps porosity and surface area fixed during reactive
transport; changing either field in time is not supported by the current
surface-state coupling.

- `resolved-reference` uses a 18000 x 6000 synthetic full-reference domain at
  1 micrometre resolution. It is generated from the 6000 x 6000 resolved
  full-model REV by appending two mirrored copies in the streamwise direction.
- `dbs-upscaled` uses the corresponding 3600 x 1200 DBS domain at
  5 micrometre resolution. It is generated from the 1200 x 1200 DBS
  full-model REV by the same streamwise mirroring pattern. Vugs are resolved
  and the matrix phase is assigned porosity and intrinsic surface area from
  the resolved matrix REV.

Set `DBS_COARSEN_FACTOR=2` or `3` for 10 or 15 micrometre DBS cells. Geometry
is downsampled categorically by majority class: generated images contain only
`0` (matrix) and `255` (vug pore). Coarsening never creates intermediate phase
labels or accidental microporosity; matrix porosity remains the explicit
closure value assigned during case initialization.

Set `RESOLVED_COARSEN_FACTOR=5`, `10`, or `15` to perform the corresponding
5, 10, or 15 micrometre **fully resolved pore/grain** calculation from the
native 1 micrometre image. This is separate from DBS coarsening. Resolved
coarsening is also categorical majority voting, so the output contains only
solid `0` and pore `255`; it never creates an intermediate microporous phase.

For this geometry, the 5 micrometre resolved image preserves streamwise pore
connectivity and matches the native porosity closely. The tested 10 and
15 micrometre categorical images lose streamwise pore connectivity and are not
valid transport meshes.

## Reproducing the runs and paper figures

The committed templates, compressed input images, and launch scripts are the
complete run inputs. Generated meshes, decomposed fields, logs, and results are
deliberately ignored. From a clean checkout, preview a matched production pair
before submitting it:

```bash
OTHER_PE_SWEEP=3 ./prepare_archer_other_pe.sh
CONFIRM_OTHER_PE_SUBMIT=1 OTHER_PE_SWEEP=3 ./prepare_archer_other_pe.sh
```

Repeat with `OTHER_PE_SWEEP=0.1` and `10`; submit the Pe=1 baseline with

```bash
CASE_SWEEP="resolved-reference dbs-upscaled" RESOLVED_COARSEN_FACTOR=5 \
  PE_SWEEP=1 ./submit_archer_two_scale_all.sh
```

The launchers record the full configuration under each generated run's
`results` directory.

`paper_validation_runs.json` records the exact pressure-corrected-flux output
directories and matched times used in the current figures. After copying those
outputs to the listed paths—or updating the paths to equivalent reruns—run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_paper_validation.py
```

In the established ARCHER2 workspace, the site-local `.archer2-tools/gcfoam-env.sh`
helper may be sourced instead of creating a virtual environment; that helper is
machine-specific and is intentionally not part of the committed case.

This regenerates the Pe=0.1, 1, 3, and 10 comparison metrics, asserts the
front-sensitive Pe=1 thresholds, and enforces the shaded acceptance limits for
both aqueous and sorbed Li: 5% inventory error, 10% normalized profile L1, and
0.1 map dissimilarity. It writes all intermediate artifacts under ignored
`results/paper_figures` and publishes the two final PNGs to the paper-standard
`../../figures/png` directory. The field figure is rendered on the native
5 micrometre grid: resolved grains are masked, and no averaging or intermediate
microporous phase is introduced.

For ARCHER submission on a different installation, either load a complete
GeoChemFoam/OpenFOAM environment before calling the launchers or point them to
a site helper:

```bash
export GCFOAM_ENV_FILE=/absolute/path/to/gcfoam-env.sh
```

The helper path is forwarded to each Slurm job; no checkout-specific path is
embedded in the committed production runner.

Run the complete benchmark with:

```bash
./runAll.sh
```

For a Pe sweep:

```bash
PE_SWEEP="1 0.3 0.1" RT_CHECKPOINT_COUNT=10 ./runPeSweep.sh
```

`RT_CHECKPOINT_COUNT` controls the number of intermediate
reactive-transport write intervals. The default of ten writes snapshots at
10%, 20%, ..., 100% of the run. Because each Pe run computes its own total
runtime from the matched pore velocity, these outputs align by normalized front
position for presentation. Before
reactive transport starts, `runAll.sh` writes `results/preflight_summary.md`
with the calibrated Pe checks, flow rates, estimated front travel times, and
chosen runtime. The production runtime targets the advective front reaching the
outlet (`x/L = 1`) and applies a safety factor, so lower-Pe cases run for
proportionally longer physical times.

Reactive-transport timesteps are computed after flow calibration from the
maximum cell-centre velocity in the actual calibrated field. That velocity is
scaled to the requested flow and multiplied by a face-interpolation safety
factor:

```text
deltaT = RT_CFL_TARGET * dx / (measuredDesignVelocity)
```

The defaults are `RT_CFL_TARGET=0.5`, `RT_FACE_VELOCITY_SAFETY=1.25`, and no
minimum guessed local-velocity factor or maximum timestep cap
(`RT_LOCAL_VELOCITY_FACTOR=0`, `RT_TIMESTEP_MAX=0`). Override with
`RT_TIMESTEP_OVERRIDE` only for explicit convergence or scaling tests.
The full 5 um resolved CFL study is documented in
`results/resolved_resolution_study/README.md`; CFL 0.5 gave a 0.232% Li L2
difference and a 0.080% total-Li inventory difference relative to CFL 0.25.
Operational acceptance has passed, but overall scientific acceptance remains
provisional pending the documented native-1-um versus 5-um spatial sorption
metrics. Until those pass, the full Pe=1 resolved run is classified as a
production pilot rather than the final resolution-independent result.

Fresh reactive transport must preserve the pressure-corrected `phi` produced
by the flow solve. Do not delete it or reconstruct it from cell-centred `U`.
The runners reject a fresh parallel launch unless every `processor*/0/phi` is
present, and the solver defaults to `rebuildPhiFromU false`. Before production,
the matched 90-step inert/reactive check must have no more than 0.1% total-Li
difference after including the PHREEQC dump surface inventory. The Pe=1 cases
completed before this safeguard are invalidated and must be rerun.

The input images are copied from the dispersion-paper image set into
`shared/source`. Derived domains and REV metadata are regenerated by
`scripts/prepare_images.py`. Matrix REV closure properties are written to
`results/matrix_rev_properties.json` by
`scripts/compute_matrix_rev_properties.py`; the default permeability and
Pe-dependent effective dispersion model are taken from the dispersion-paper
matrix REV values and can be overridden through environment variables if a
different closure data source is used. The DBS reactive-transport run uses the
longitudinal component of that matrix dispersion fit as its scalar effective
diffusion input for the selected Pe.

## HPC handoff

Production and restart jobs are pinned to the reviewed runtime identity in
`production_runtime_identity.json`:

- runtime commit `e7b486b68fac48544ca394cd27cf408214b40dd9`;
- runtime tree `26a39f2e4487162d9631502a94c258500e1b8709`;
- PhreeqcRM commit `8ce64cf64b3c26ff7fdc41dbf5ae4fb7269b3a92`;
- solver SHA-256 `b8762ed35691ed9edf809866e4a39382cfa3d1a9b7f589fc0a02b35eff38290d`;
- reaction-library SHA-256 `897f16b1aab58b34b3c60d24dd7e9d2f56f32501cf955fe9fd4ad0039384ed1e`;
- PhreeqcRM-library SHA-256 `cfa877676ec21145ad60390c992dc7d80773ac4151c3c7c297d3de8ea8cc330a`.

`runSingleCase.sh` verifies the commit, tree, submodule, artifact hashes, and
dynamic-library resolution before generating geometry or running a solver. It
writes `results/runtime_preflight.json`, and matched-run provenance repeats the
same validation at initial and final stages. Set `GCFOAM_RUNTIME_ROOT` or
`GCFOAM_DIR` to the reconstructed runtime checkout. A different commit or
binary fails closed even if it is otherwise clean.

Commit the case templates, scripts, and compressed source images in
`shared/source`. Do not commit generated `.raw` domains, `processor*`
directories, `0` directories, logs, `.out` files, or `results`; these are
ignored locally and are regenerated by the run scripts.

The full resolved reference domain contains 108 million cells, so production
runs should be launched on a machine with substantially more resources than a
desktop workstation. The case decomposition is controlled in each
`createMesh.sh` through `NPX`, `NPY`, and `NPZ`; the current portable default is
`8 x 4 x 1` (32 MPI ranks). Increase this on the target machine if the scheduler
allocation supports it.

Before committing to a 24-hour production allocation, run the resolved-reference
strong-scaling harness:

```bash
sbatch submit_archer_resolved_scaling.slurm
```

Edit the Slurm account and environment setup in
`submit_archer_resolved_scaling.slurm` before submission. The default scaling
points are `512`, `1024`, and `2048` MPI ranks, specified as
`SCALING_SPECS="32x16x1 32x32x1 64x32x1"` on a 16-node ARCHER2 allocation.
Increase the node count and add a larger decomposition, for example
`64x64x1`, if 4096 ranks are needed. The scaling harness runs the full 108M-cell
resolved mesh with a short reactive-transport window and a calibrated
CFL-based timestep, then writes timing artifacts under `results/scaling/`. Use
the reported Courant number from the short resolved run to adjust
`RT_CFL_TARGET` or `RT_LOCAL_VELOCITY_FACTOR` before production. Use those
timings to choose the smallest node count that can finish the required Pe case
within the site wall-time limit.

Reactive writes include a `phreeqc.dmp` checkpoint containing the complete
aqueous and surface state. To continue an existing case without rerunning mesh,
flow, or reactive initialization, enter its `resolved-reference` or
`dbs-upscaled` directory and run:

```bash
RT_RESTART=1 RT_TOTAL_TIME=<new-absolute-end-time> ./runCaseReactiveTransport.sh
```

The runner selects the newest time containing both `phreeqc.dmp` and the
`phreeqc.complete` marker written only after the matching OpenFOAM fields
have succeeded. Set `RT_RESTART_TIME=<time>` to select a specific complete
checkpoint instead; an incomplete or missing requested checkpoint is rejected.
Checkpoints are intentionally complete and can be large. The
4.32-million-cell DBS smoke used approximately 19.17 GiB for each retained
checkpoint, including its PHREEQCRM dump and OpenFOAM fields. The submission
guard budgets 5.0 kB per cell for every requested checkpoint, plus 5 GiB of
fixed overhead. Ten checkpoints therefore require approximately 206 GiB of
scratch per DBS job and 413 GiB for a matched pair. Completed checkpoints are
retained and remain restartable in the persistent `archer_work` case directory.

For production Pe/case runs on ARCHER2, submit each case as a separate job. The
single-case runner is:

```bash
TARGET_CASE=resolved-reference TARGET_PE=1 ./runSingleCase.sh
TARGET_CASE=dbs-upscaled TARGET_PE=1 ./runSingleCase.sh
```

On ARCHER2, the safe default submits only the validated DBS cases for
`Pe=1 0.3 0.1`:

```bash
./submit_archer_two_scale_all.sh
```

For a matched surface-reconstruction sensitivity pair, give each job an
explicit nontechnical label and select its reconstruction through the case
environment:

```bash
SURFACE_RECONSTRUCTION_LABEL=supported \
ASURF_SURFACE_MODE=occupancyGaussian \
TWO_SCALE_ARCHIVE_MODE=selected \
PE_SWEEP=1 CASE_SWEEP=dbs-upscaled ./submit_archer_two_scale_all.sh

SURFACE_RECONSTRUCTION_LABEL=legacy-reference \
ASURF_SURFACE_MODE="$LEGACY_REFERENCE_MODE" \
TWO_SCALE_ARCHIVE_MODE=selected \
PE_SWEEP=1 CASE_SWEEP=dbs-upscaled ./submit_archer_two_scale_all.sh
```

The label is included in the scratch/archive directory and Slurm job name.
`results/matched_run_provenance_<label>.json` records the matched input hashes,
surface-field hashes, runtime and solver identity, Slurm stages, and complete
final checkpoint fields. The jobs must use the same clean paper and runtime
commits and differ only in `ASURF_SURFACE_MODE` and their labels.

After both Pe=1 DBS jobs finish cleanly, verify the complete matched pair with:

```bash
python3 scripts/analyze_matched_reconstruction_pair.py \
  --supported-case /archive/supported/dbs-upscaled \
  --legacy-reference-case /archive/legacy-reference/dbs-upscaled \
  --supported-provenance /archive/supported/results/matched_run_provenance_supported.json \
  --legacy-reference-provenance /archive/legacy-reference/results/matched_run_provenance_legacy-reference.json \
  --output-json results/matched_reconstruction_full_horizon.json \
  --output-figure results/matched_reconstruction_full_horizon.png
```

The analyzer fails closed unless provenance proves matched inputs and runtime,
the reconstructed surface field is the sole intended difference, Slurm exited
cleanly, and all ten common checkpoints span the requested horizon. At every
checkpoint it tests reactive area, aqueous and sorbed Li inventories, spatial
normalized L1, map cosine, and x50 positions against the predeclared limits
recorded in the JSON. Native-cell inventory-density L2 remains a prominent
non-gating diagnostic because it includes the deliberate relocation of reactive
area between cells; fixed-reference-area sorption L2 separates that relocation
from the chemistry response. The x10 and x90 positions are likewise diagnostic.
The figure uses shared value scales for each matched map pair and a separate
signed-difference scale. `--early-test` is only for pipeline checks;
its JSON and figure explicitly state that it cannot establish a full-horizon
claim.

Preview the three `sbatch` commands without submitting with
`SUBMIT_DRY_RUN=1 ./submit_archer_two_scale_all.sh`.
The sweep refuses inherited smoke/restart controls such as `RT_TOTAL_TIME`,
`RT_TIMESTEP_OVERRIDE`, or `RT_RESTART`; unset them before production.
Deliberate diagnostic overrides require `ALLOW_RT_OVERRIDES=1`.

To request the much larger resolved-reference jobs, opt in explicitly:

```bash
CASE_SWEEP=resolved-reference ./submit_archer_two_scale_all.sh
```

For the validated 5 micrometre resolved mesh, use:

```bash
CASE_SWEEP=resolved-reference RESOLVED_COARSEN_FACTOR=5 \
  ./submit_archer_two_scale_all.sh
```

Non-baseline matched resolved/DBS cases have a guarded launcher that pins this
5 micrometre configuration. Its default `Pe=0.3 0.1` sweep previews all four
`sbatch` commands and submits nothing:

```bash
./prepare_archer_other_pe.sh
```

After reviewing the preview, submit exactly those four jobs with
`CONFIRM_OTHER_PE_SUBMIT=1 ./prepare_archer_other_pe.sh`.
Select one matched pair with, for example,
`OTHER_PE_SWEEP=3 ./prepare_archer_other_pe.sh`. Supported non-baseline values
are `0.1`, `0.3`, `3`, and `10`.

For the high-Pe failure search, run `Pe=3` before `Pe=10`. Pe=3 is a clean
stress test within the same longitudinal-dispersion closure branch as Pe=1.
Pe=10 is exactly the branch transition: the DBS longitudinal multiplier jumps
from about 2.396 immediately below 10 to 2.695 at 10. A mismatch observed only
at Pe=10 therefore cannot by itself distinguish loss of upscaling accuracy
from sensitivity to that closure transition.

Native 1 micrometre resolved-reference jobs request 128 nodes
(`256 x 64 x 1`, 16384 ranks). Coarsened resolved jobs default to the measured
CU-efficient 8-node layout (`40 x 24 x 1`, 960 ranks), and DBS jobs request 2 nodes (`32 x 8 x 1`,
256 ranks). Each job copies the committed template into a per-job scratch
working directory, runs only its assigned Pe/case pair, and synchronizes
results back to `results/archer/<case>_<Pe>_<jobid>/`. Override
`RESOLVED_NPX`, `RESOLVED_NPY`, `DBS_NPX`, or `DBS_NPY` at submission time if
the site-specific performance test suggests a better layout.

The default `TWO_SCALE_ARCHIVE_MODE=metadata` copies logs, summaries, and
configuration while leaving the large per-rank fields in the persistent work
directory. This avoids spending compute allocation time duplicating thousands
of field files. Use `TWO_SCALE_ARCHIVE_MODE=selected` to copy selected species
fields, or `full` for a complete duplicate, when that extra copy is required.

Before submitting production jobs, estimate storage for each run and confirm
that both scratch and archive filesystems have enough free space below quota.
`submit_archer_two_scale_case.slurm` includes a conservative disk-space
preflight and exits before running if either filesystem is too small. The
archive estimate follows `TWO_SCALE_ARCHIVE_MODE`; metadata mode does not
require space for a second copy of the persistent fields and PHREEQC dumps.
The preflight records its model, byte requirements, paired requirements, and
observed free space in `results/storage_preflight.env`. Overrides may increase
but cannot reduce the modeled requirements. The ARCHER project quota and the
combined capacity for both matched jobs should still be checked explicitly on
the target system.

If a production run reaches the 24-hour site limit, continue its newest
complete checkpoint in the existing work directory with:

```bash
./submit_archer_restart.sh \
  archer_work/two_scale_dbs-upscaled_pe_1_JOBID/dbs-upscaled \
  203.61105
```

The second argument is the final absolute simulation time. The helper reloads
the saved timestep and write interval from `results/current_run_config.env`.
By default it selects and validates the newest complete PHREEQC checkpoint and
slightly aligns the restart write interval so the requested endpoint is a
scheduled write. The reactive runner then exits nonzero unless the final Li
field, PHREEQC dump, and completion marker exist on every partition within one
timestep of the requested end time. Set `RT_ALIGN_FINAL_WRITE=0` only for a
deliberate diagnostic that must retain the previous cadence.
Set `RT_RESTART_TIME=<time>` only when a specific complete checkpoint is
required.
