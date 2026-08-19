# ARCHER/Codex Handoff: Two-Scale Micromodel Sorption Runs

This directory contains the reproducible two-scale lithium sorption benchmark
for the surface-complexation paper. The goal is to compare a fully resolved
micromodel reference against an upscaled DBS representation of the same
physical domain at multiple Peclet numbers.

## Scientific Intent

- Chemistry: simplified direct-lithium-extraction-style Li sorption from a
  Na/K/Mg brine onto a generic surface site.
- Geometries:
  - `resolved-reference`: full resolved micromodel, 18000 x 6000 x 1 cells at
    1 micrometre resolution.
  - `dbs-upscaled`: equal physical domain, 3600 x 1200 x 1 cells at
    5 micrometre resolution. Vugs are resolved; matrix porosity, intrinsic
    surface area, and longitudinal effective diffusion come from the matrix REV.
- Figure sweep: `Pe=0.1 1 3 10`; `Pe=0.3` remains a supported optional case.
- Runtime target: the advective front reaches the outlet (`x/L = 1`) with a
  safety factor. Lower-Pe jobs therefore run for proportionally longer physical
  times.
- Comparison target: aqueous transport, surface area controlled sorption, and
  total/local sorbed inventory differences between resolved and DBS cases.

## Important Rules

- Restart only from a written time containing `phreeqcDBS.dmp`; run
  `RT_RESTART=1 RT_TOTAL_TIME=<new-absolute-end-time>
  ./runCaseReactiveTransport.sh` inside the case directory.
- Preserve the pressure-corrected `phi` produced by the completed flow solve.
  Never delete it or reconstruct it from cell-centred `U`; that path caused a
  cumulative resolved-case mass error. Fresh reactive launches now require
  `0/phi` (or every `processor*/0/phi`) and use `rebuildPhiFromU false`.
- Do not run multiple Pe/case jobs in the same working directory. Each ARCHER
  job must copy the committed template into a separate scratch directory.
- Do not commit generated raw domains, `processor*`, `0`, logs, `.out` files,
  or `results`. The local `.gitignore` is set up for this.
- Complete PHREEQC checkpoints are restartable but storage-heavy. Preserve the
  full scratch case, or use full archive mode, when a later Slurm continuation
  will be required.
- Restart submissions align their write interval to the requested final time,
  and completed reactive jobs are rejected unless the final Li field, PHREEQC
  dump, and completion marker exist on every partition. This prevents a clean
  solver exit without a scientifically usable endpoint.
- Prepare matched non-baseline 5 um pairs with
  `OTHER_PE_SWEEP=<value> ./prepare_archer_other_pe.sh`; supported values are
  `0.1`, `0.3`, `3`, and `10`. It is preview-only unless
  `CONFIRM_OTHER_PE_SUBMIT=1` is set. Test Pe=3 before Pe=10: Pe=10 is exactly
  the DBS longitudinal-dispersion closure branch transition, so failure there
  alone would be ambiguous.

## Timestep/CFL Policy

The production scripts calculate timestep from the calibrated maximum
cell-centre velocity, the 1.25 face-velocity safety factor, and a target CFL:

```text
deltaT = RT_CFL_TARGET * dx / measuredDesignVelocity
```

Default values:

```text
RT_CFL_TARGET=0.5
RT_FACE_VELOCITY_SAFETY=1.25
RT_LOCAL_VELOCITY_FACTOR=0
RT_TIMESTEP_MAX=0
```

Use `RT_TIMESTEP_OVERRIDE` only if intentionally forcing a single timestep for
diagnostics. Do not use a stale `RT_TIMESTEP` environment variable to drive a
production sweep. Full 5 um resolved jobs `14586522`--`14586524` compared CFL
0.25, 0.5, and 0.7 over 140/70/50 real chemistry steps. CFL 0.5 changed the Li
field L2 norm by 0.232% and total Li inventory by -0.080% relative to 0.25, so
0.5 is the selected conservative production default.

## Runtime Policy

The production run duration is recomputed for each Pe from the Pe-matched pore
velocity:

```text
front_time = L / pore_velocity
RT_TOTAL_TIME = runtime_safety_factor * max(front_time_resolved, front_time_DBS)
```

The default `runtime_safety_factor` is `1.25`. Approximate timings from the
current Pe=1 calibration are:

```text
Pe=1    RT_TOTAL_TIME ~ 204 s
Pe=3    RT_TOTAL_TIME ~ 68 s
Pe=10   RT_TOTAL_TIME ~ 20 s
Pe=0.3  RT_TOTAL_TIME ~ 679 s
Pe=0.1  RT_TOTAL_TIME ~ 2036 s
```

These are longer than the earlier exploratory local runs, which targeted only
partial front penetration.

The default `RT_CHECKPOINT_COUNT` is `10`. The write interval is
`RT_TOTAL_TIME / RT_CHECKPOINT_COUNT`, so outputs are written at 10%, 20%, ...,
100% of each run. This keeps the resolved and DBS cases aligned by normalized
front position for presentation even though lower-Pe cases run for longer
physical times.

## Files To Know

- `README.md`: human-facing overview.
- `runAll.sh`: local full benchmark for one Pe, both cases sequentially.
- `runPeSweep.sh`: local sequential Pe sweep, both cases for each Pe.
- `runSingleCase.sh`: one `(TARGET_CASE, TARGET_PE)` run. This is the cluster
  production entry point.
- `submit_archer_two_scale_case.slurm`: one ARCHER job for one case and one Pe.
- `submit_archer_two_scale_all.sh`: guarded multi-job launcher. Its safe default
  submits DBS only for `Pe=1 0.3 0.1`; request resolved jobs explicitly.
- `prepare_archer_other_pe.sh`: preview-first matched 5 um launcher for
  non-baseline `Pe=0.1`, `0.3`, `3`, and `10` pairs.
- `paper_validation_runs.json`: exact valid output paths and matched times used
  by `scripts/reproduce_paper_validation.py` for the current paper figures.
- `submit_archer_resolved_scaling.slurm`: short scaling/timing harness for the
  resolved reference.
- `shared/source/*.raw.tar.gz`: committed source images. Derived `.raw` domains
  are generated by `scripts/prepare_images.py`.

## ARCHER Submission Workflow

1. Start from a clean checkout of this branch.
2. Build/source GeoChemFoam on ARCHER so `GCFOAM_DIR`, OpenFOAM, PHREEQC, and
   the custom solvers are available.
3. Override `GCFOAM_SLURM_ACCOUNT` or `GCFOAM_SLURM_QOS` if the target
   allocation differs from the committed ARCHER2 defaults. Source the
   GeoChemFoam environment if the submission shell does not already do it.
4. Before submitting, check project quota and filesystem capacity. Estimate the
   scratch and archive requirement for each `(case, Pe)` job, then confirm both
   filesystems have that much free space below quota. The Slurm script performs
   a conservative `df`-based preflight and exits before running if either
   scratch or archive space is below the estimate, but the agent should still
   inspect quota explicitly on the target system.
5. From this directory, preview a matched non-baseline pair:

```bash
OTHER_PE_SWEEP=3 ./prepare_archer_other_pe.sh
```

Set `CONFIRM_OTHER_PE_SUBMIT=1` only after reviewing the preview.

By default the submit-all helper requests:

```text
resolved-reference: nodes=128, total MPI ranks=16384, decomposition=256 x 64 x 1
dbs-upscaled:       nodes=2,  total MPI ranks=256,  decomposition=32 x 8 x 1
ntasks-per-node=128 for both
walltime=24:00:00
```

Each Slurm job copies this directory to a per-job scratch path and runs exactly
one case:

```bash
TARGET_CASE=resolved-reference TARGET_PE=1 ./runSingleCase.sh
TARGET_CASE=dbs-upscaled TARGET_PE=1 ./runSingleCase.sh
```

The guarded non-baseline helper pins the validated 5 um resolved geometry and
generates one resolved and one DBS submission per requested Pe.

## Output Locations

During the run, each job uses a scratch directory:

```text
${SCRATCH:-$SLURM_SUBMIT_DIR/archer_work}/two_scale_<case>_pe_<Pe>_<jobid>
```

At exit, the Slurm script synchronizes selected outputs back to:

```text
results/archer/two_scale_<case>_pe_<Pe>_<jobid>/
```

Important files there:

- `results/current_run_config.env`
- `results/preflight_summary.md`
- `results/matched_pe_flow_rates.json`
- `<case>/reactiveTransportDBSFoamRT.out`
- `<case>/simpleDBSFoamFlow.out`
- `<case>/processPoroPermFlow.out`
- selected processor time fields for aqueous and sorbed species

## Disk and Quota Preflight

Before launching production jobs, estimate required storage for each case and
compare it with both scratch and archive quota. The submitted job writes full
OpenFOAM processor fields during runtime and then synchronizes selected fields
for analysis. With ASCII OpenFOAM fields and ten output intervals, a resolved
case can require hundreds of gigabytes to more than a terabyte of working space
depending on how many fields are retained.

The Slurm script estimates storage from:

```text
cells * bytes_per_scalar_ascii * archived_fields * write_count
```

with additional runtime and safety multipliers. It reports:

```text
estimated_required
scratch_available
archive_available
```

and exits before copying/running if either filesystem is too small. On ARCHER,
also run the site quota command for the relevant project/work filesystems
before submission, because `df` free space does not necessarily mean the project
quota is available.

## Post-Run Checks

For each completed job:

1. Check `slurm_exit_code.txt` is `0`.
2. Inspect `reactiveTransportDBSFoamRT.out` for `FOAM FATAL`,
   `PHREEQC error`, solver stalls, or missing final time.
3. Confirm `results/current_run_config.env` has the expected `TARGET_CASE`,
   `TARGET_PE`, `RT_TIMESTEP`, `RT_TOTAL_TIME`, and decomposition.
4. Confirm the first and final written times exist in processor directories.
5. For Pe=1, inspect the early checkpoint before trusting the rest of the run:
   the Li front should move consistently with the flow-derived pore velocity.
6. Confirm the solver reports `Using pressure-corrected phi read by createPhi`.
   In a matched 90-step inert/reactive smoke test, require total-Li agreement
   within 0.1% after adding the PHREEQC dump surface inventory.
7. At the final time, confirm the front has reached or passed the outlet before
   using the run in the paper figures.

## Why Jobs Are Split

The resolved reference has 108 million cells and reactive transport is
expensive. Running the sweep sequentially would exceed local and
likely cluster wall-time limits. Splitting by `(case, Pe)` also prevents jobs
from overwriting each other because OpenFOAM writes into fixed case directories
such as `resolved-reference/processor*`.

## Reproducing the paper plots

Completed decomposed fields remain ignored because of their size. The exact
valid pressure-corrected-flux sources and times are recorded in
`paper_validation_runs.json`. After those outputs are present, create the
Python environment documented in `README.md` and run
`python3 scripts/reproduce_paper_validation.py`. The driver regenerates the
metrics, asserts the Pe=1 front thresholds, and publishes the final PNGs under
the paper-standard `../../figures/png` directory.
