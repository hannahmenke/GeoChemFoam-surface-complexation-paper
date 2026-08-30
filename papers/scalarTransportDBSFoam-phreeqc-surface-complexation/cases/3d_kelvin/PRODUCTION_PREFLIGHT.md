# Kelvin local-production preflight

This is a launch gate, not a result record.  Kelvin production is local only.
Do not launch until every item labelled **required** below has passed against
one immutable case tree and one immutable runtime.  This file does not
authorise changing or deleting any preserved pilot.

## Evidence snapshot and terminology

Evidence was inspected on 2026-08-30.  Values are labelled as follows.

- **Measured**: read from a completed run, filesystem, repository, or remote
  pull-request state.
- **Derived**: arithmetic from measured values; the formula is given.
- **Assumed**: a planning margin or acceptance threshold that must be retained
  or explicitly revised before launch.

The paper baseline for this preflight is exact commit
`019f7e4c2ec70db638685bcb5729a202056f52e2`.  The three completed pilot cases
are preserved under `/tmp/gcf-kelvin-final-pilot-dt*`; the active finer pilot
was neither inspected nor modified for this preflight.

## Current hard blockers

### 1. Final restart-capable runtime does not yet exist

**Measured remote state:** the dependency chain is still open and draft.

| Repository PR | Required reviewed head | State at snapshot |
|---|---:|---|
| `GeoChemFoam/phreeqcrm#6` | `9f7f00ca4417dd035dd234d2a60ae2e2f6ab1a53` | open draft; no human review |
| `GeoChemFoam/phreeqcrm#7` | `f060d41dc70b5c10141192a5db6cf7c9189d6514` | open draft; no human review; based on PR 6 |
| `GeoChemFoam/GeoChemFoam-v-dev#53` | `a1c4b5693f62bfa56cdba875b794e10b96f5c805` | open draft; no human review |

PR 53 still pins temporary PHREEQCRM commit
`8ce64cf64b3c26ff7fdc41dbf5ae4fb7269b3a92`; the tracked PHREEQCRM branch is
still at `8aa2a9047d883d295b9afadab50df3234abd9d66`.  A fresh ordinary submodule
checkout therefore cannot yet reproduce the intended combined runtime.

**Required merge/build order:**

1. Obtain human approval and merge PR 6 with a merge commit, preserving its
   reviewed head in the permanent PHREEQCRM branch.
2. Retarget PR 7 to that permanent branch without rewriting its reviewed head;
   confirm it remains exactly three commits and six files ahead, rerun its
   validation, obtain human approval, and merge it with a merge commit.
3. Repin PR 53 to the resulting permanent PR-7 merge tip.  Prove that
   `git submodule update --init --recursive` works in a fresh clone without
   fetching pull-request refs.  Run the full repository commit gate against
   that exact pin, obtain human approval, and merge PR 53.
4. Build a clean local runtime from the resulting GeoChemFoam `main`.  Record
   the GeoChemFoam commit and tree, PHREEQCRM commit and tree, solver SHA-256,
   relevant shared-library SHA-256 values, compiler/OpenFOAM identity, and a
   clean tracked-diff digest.

Production and its acceptance pilots must use that exact final runtime.  The
completed pilots used interim GeoChemFoam commit
`3c4a34326b5573d76d48664093a1933a5a65b316`, PHREEQCRM commit
`a43de2c1d1dd5c0f93489d560fa3cd3e94646471`, and solver SHA-256
`3b41fd0914b4407fa591ea403cc66c4fde1daa7d1608481edaac19533e11b124`.
Those measurements are valid for planning, but they cannot certify a different
merged production binary.

### 2. The tracked Kelvin case is not the pilot-tested case

**Measured:** the reviewed paper head tracks HFO-prefixed Kelvin surface-field
names, whereas every completed pilot uses the project `Surf_*` case convention.
The reviewed renderer wrapper also asks for HFO-prefixed fields, while the
pilots actually wrote `Surf_sOMn+`, `Surf_wOMn+`, and `Surf_wOMg+`.

Seven logical tracked inputs differ; the first row comprises both the template
and realised dictionary, so eight file paths differ:

| Logical input in `tutorials/.../3DKelvinSurfaceComplexation` | Reviewed SHA-256 | Pilot SHA-256 | Material difference |
|---|---:|---:|---|
| `constant/thermoPhysicalProperties{,1}` | `ff8793b418b15cf3874a9c169f6b910a807ad875b81cc382403ebb4228e5694c` | `91b7d1229e4d3758000b7069486cc791a6ae5a5ca4e3375677f21201e81cee77` | HFO-prefixed fields/masters versus `Surf_*` |
| `constant/phreeqcReactions` | `ff378541ec4ee4ab6ad5603aa5724c632a9f73b1438cdd79a67d74126a463e62` | `fae65265504bb6166ee72ed69b78f995cbee6c5f9a9d6055d07dadef19912a76` | matching PHREEQC names and selected output |
| `system/controlDict1` | `d451ebc96ab88ff10f10245a00220782041283df45c74df4a542c76f8e12f276` | `79c401347771ab95e4859bcb8c4b855a9417c562230cf690adc57e5542253335` | explicit restore switch |
| `system/fvSolution1` | `7d5613e3664a04c736614e991acb75f027ddfa4a36aac80d6acd1e7d01d421aa` | `40e0c0c721d360ed8217479cb8f30632c020b95fc7e852a423d5c25e7d6d2392` | tighter scalar solve and zero relative tolerance |
| `runCaseFlow.sh` | `956e144256256a2db00cd69985cc31ee09f38b5e3c3a46e35e5028919a263260` | `cb8c11f671bf16974850132d3741747bca9a21389dd034eee2769447b2aad830` | explicit flow-duration override |
| `initCaseReactiveTransport.sh` | `ea2a9b7a174ea23fafe1e0d81ea542463aafb401e8c379300f0d011e92b39080` | `abd6bb498e9cf35f931611ecbc534657e90ac3ddb2f66e3fd4e29e7fe25208ec` | runtime isolation, provenance, and `Surf_*` fields |
| `runCaseReactiveTransport.sh` | `2a2f589d41a7c19a6bc56caa76d74505b21105b1da5572f686a81d615175ed2e` | `962fade27bac9567c09cfb1cee27d957aa13411fcd1885313102004e9fc01721` | runtime isolation, pilot timestep, and run manifest |

The pilot `kelvin_provenance.py` is also absent from the reviewed tree, and the
pilot cases contain untracked realised inputs and outputs.

**Minimum coherent remediation, required before rerunning acceptance pilots:**

1. Commit and independently review the pilot-tested `Surf_*` Kelvin input
   bundle, runtime isolation, and provenance recorder as one case change.
2. Change only the generic renderer wrapper's field arguments from the stale
   HFO-prefixed names to the resulting tracked `Surf_*` names; the Python
   renderers already accept field names as arguments.  Do not add ion-name or
   surface-name special cases to solver or adapter code.
3. Regenerate a clean case from that commit and prove its manifest covers every
   case, chemistry, geometry, decomposed initial-field, runtime, solver, and
   linked-library input.  No local patch or untracked input may remain.

## Timestep-convergence gate

The 32-rank pilots used identical 200 x 200 x 200 meshes, a 2 x 4 x 4
decomposition, a 0.5 s endpoint, and one matched checkpoint.  Completed-run
measurements are:

| `deltaT` [s] | Detached wall [s] | Solver clock [s] | mean Co | max Co | status | checkpoint pairs |
|---:|---:|---:|---:|---:|---:|---:|
| 0.0015625 | 6,808 | 6,799 | 0.0581960 | 0.201417 | 0 | 32/32 |
| 0.00078125 | 13,544 | 13,535 | 0.0290980 | 0.100709 | 0 | 32/32 |
| 0.000390625 | 26,131 | 26,121 | 0.0145490 | 0.0503543 | 0 | 32/32 |

The completed adjacent comparison `0.00078125` versus `0.000390625` did not
pass: sorbed-Mn global relative L1 difference was 4.1473%, although all Mn
inventory differences were below 1% and front positions agreed within one
cell.  Therefore `0.00078125` is not a production timestep.

**Required:** after the final runtime and tracked `Surf_*` case exist, run the
matched `0.000390625`/`0.0001953125` pair again on that exact identity.  The
comparison artifact must validate every recorded hash, all 32 checkpoint
pairs, identical mesh/initial fields/chemistry, and all of these criteria:

- each aqueous, sorbed, and total Mn inventory difference is below 1%;
- global relative L1 differences for aqueous and sorbed Mn are below 1%;
- Mn front positions at the 10th, 50th, and 90th inventory percentiles differ
  by no more than one 10 micrometre cell and by less than 1% of domain length;
- all values are finite and all required nonnegative fields remain
  nonnegative.

If it passes, select `deltaT = 0.000390625 s`.  If it fails, do not launch;
continue timestep refinement.  The measured maximum Co of 0.0503543 at the
candidate timestep is intentionally conservative.  Timestep selection is
controlled by the chemistry/distribution comparison, not by trying to raise
Co.  Measure and record Co again on the final runtime.

## Mandatory 32-versus-64-rank preflight

The host provides **measured** 64 physical cores (128 hardware threads), two
NUMA nodes, and 1,079,606,603,776 bytes of RAM.  Only 32-rank runtime is
measured; 64-rank speed and aggregate memory are unknown.

After timestep acceptance, create two clean, manifest-identical benchmark
copies.  Use 2 x 4 x 4 decomposition for 32 ranks and balanced 4 x 4 x 4 for
64 ranks (250,000 and 125,000 cells per rank, respectively).  Run each from
0 to 0.025 s with the accepted timestep, one endpoint checkpoint, one thread
per rank, core binding, and no other CPU-intensive job.  Record total detached
wall time, solver-only time before checkpoint I/O, checkpoint time and bytes,
aggregate peak resident memory, Co, field extrema, inventories, and hashes.

The 64-rank result is eligible only when:

- the two benchmark manifests differ only in decomposition/rank count;
- both complete cleanly with a valid checkpoint pair on every rank;
- 32/64 global aqueous, sorbed, and total Mn inventories and global Mn L1
  distributions agree within 0.1%, and front locations agree within one cell;
- speedup `S = T32_compute / T64_compute` is at least 1.25 (parallel efficiency
  `S/2` at least 62.5%);
- aggregate peak RSS remains below 80% of physical RAM; and
- the storage calculation below is repeated using the larger measured
  32- or 64-rank checkpoint footprint.

Otherwise retain 32 ranks and explicitly accept its projected duration, or
stop and improve scaling.  Never switch rank count or decomposition across a
restart chain.

## Wall-time projection

**Measured:** the `deltaT = 0.000390625 s`, 32-rank pilot required 26,121 s of
solver clock for 0.5 s simulated time.

**Derived conservative baseline:**

```text
T120,32 = 26,121 s x (120 / 0.5) = 6,269,040 s
         = 1,741.4 h = 72.5583 d
```

**Assumed planning contingency:** 10%, giving 79.8142 d at 32 ranks.  After
the strong-scaling test, project `T120,64 = T120,32 / S`, then add the measured
cost of fourteen checkpoint writes, thirteen restores, and 10% contingency.
Do not advertise a 64-rank duration before measuring `S`.

## Retained output and disk gate

The figure renderers need baseline time 0, final time 120, and temporal data at
12 s spacing.  Retain this nonuniform schedule:

```text
0, 1, 2, 4, 8, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120 s
```

Times 1, 2, 4, and 8 resolve early exchange and support chemistry/mass checks;
times 12 through 120 are the exact temporal-figure series; time 120 also
supports the three-dimensional field figure.  There are fourteen written
post-initial checkpoints.

**Measured at 32 ranks:** one complete endpoint occupies 29,772,206,080
allocated bytes (26,591,259,783 bytes are PHREEQCRM dumps); the mesh, constant
data, and time 0 occupy 3,210,031,104 allocated bytes.  The completed case
contains 864 endpoint files and 32 valid dump/marker pairs.

**Derived using the measured candidate footprint:**

```text
base + 14 checkpoints = 3,210,031,104 + 14 x 29,772,206,080
                      = 420,020,916,224 bytes
25% reserve           = 105,005,229,056 bytes
minimum free space    = 525,026,145,280 bytes (488.969 GiB)
```

The 25% reserve is an **assumption** covering filesystem variation, logs,
manifests, benchmark evidence, and a failed partial write.  Snapshot free
space was 590,503,460,864 bytes, but that value is not a launch approval.
Immediately before production, remeasure free bytes after all pilots and
benchmarks have settled and recompute with the larger 32/64 checkpoint size.
Do not launch if free space is below the recomputed minimum.  Do not use
`purgeWrite`; every listed checkpoint is an analysis or recovery artifact.

## Staged checkpoint and restart contract

Run one stage per adjacent pair in the retained schedule.  In a fresh
production copy, prepare the first stage with `startTime 0`, endpoint 1,
`phreeqcRestartCheckpoints true`, and `phreeqcRestoreCheckpoint false`.
Every subsequent stage starts from the preceding endpoint, ends at the next
listed time, keeps checkpoint writing true, and sets restore true.  Set each
stage's write interval to `end - start`; every start and endpoint above is
aligned to that interval.  Record the realised `controlDict` hash before each
launch.

**Required restart-equivalence test:** before production, compare a clean,
uninterrupted 0-to-0.025 s run with a 0-to-0.0125-to-0.025 s checkpoint restart
using the selected rank count, timestep, runtime, and inputs.  Both intermediate
and final checkpoint pairs must validate.  At 0.025 s, all fields must have the
same sizes and finite extrema; aqueous/sorbed inventories and fieldwise relative
L1 differences must agree within `1e-10`, and front indices must be identical.
Any larger restart discontinuity is a no-launch result.

Once all gates pass, prepare the first 0-to-1 s stage exactly as follows in the
fresh case (subsequent stages replace start/end/interval and set restore true):

```bash
cd /absolute/path/to/fresh-kelvin-production-case
export GCFOAM_RUNTIME_ROOT=/absolute/path/to/final-clean-runtime
source ../configure_runtime.sh
cp system/controlDict1 system/controlDict
foamDictionary system/controlDict -entry startFrom -set startTime
foamDictionary system/controlDict -entry startTime -set 0
foamDictionary system/controlDict -entry endTime -set 1
foamDictionary system/controlDict -entry deltaT -set 0.000390625
foamDictionary system/controlDict -entry writeControl -set adjustableRunTime
foamDictionary system/controlDict -entry writeInterval -set 1
foamDictionary system/controlDict -entry purgeWrite -set 0
foamDictionary system/controlDict -entry phreeqcRestartCheckpoints -set true
foamDictionary system/controlDict -entry phreeqcRestoreCheckpoint -set false
```

Use the timestep selected by the final comparison rather than the example
value above.  Hash the resulting dictionary, then use this exact detached
launch pattern for that prepared first stage:

```bash
export GCFOAM_RUNTIME_ROOT=/absolute/path/to/final-clean-runtime
export KELVIN_RANKS=32  # or 64 only if the benchmark gate selected it
/home/hm114/.codex/skills/geochemfoam-detached/scripts/run_detached.sh \
  /absolute/path/to/fresh-kelvin-production-case \
  'source ../configure_runtime.sh; export FOAM_SIGFPE=false OMP_NUM_THREADS=1; mpirun --bind-to core --map-by core -np "$KELVIN_RANKS" reactiveTransportDBSFoam -parallel > reactiveTransportDBSFoamRT_0_to_1.out' \
  kelvin_local_0_to_1
```

Use a stage-specific solver-log name and prefix containing start/end times in
the actual launch record.  The helper creates timestamped `.log`, `.pid`, and
`.status` files.  Perform exactly one startup check after two seconds: the
outer log must be nonempty, the recorded PID must exist, and the solver log
must show the intended start time/runtime.  Do not poll thereafter unless
asked.

At stage completion, require status 0, solver `End`, the intended endpoint,
and on every rank:

- `phreeqc.dmp` and `phreeqc.complete` both exist;
- no `phreeqc.complete.tmp` or other checkpoint temporary remains; and
- the marker magic, time, dump size, and dump SHA-256 all validate.

On a crash, preserve and hash the logs and incomplete artifacts first.  Select
only the latest time whose marker/dump pair validates on every rank.  Restore
with the identical runtime, inputs, timestep, rank count, and decomposition.
Never restore from a time after manual/utility field modification.  Any later
incomplete directory must be quarantined outside the restart copy; it must not
be mistaken for evidence or overwrite the last complete checkpoint.

## Production acceptance

Production is evidence only after all of the following pass.

### Completion and chemistry

- All fourteen stages have status 0, clean `End`, exact endpoints, and valid
  checkpoint pairs on every rank; no fatal, floating-point, or PHREEQC error is
  present.
- Every aqueous and surface field is finite; fields required to be
  nonnegative are nonnegative.  The numerical internal and boundary values of
  `eps` and both surface-area fields match their initial values at every
  checkpoint (file headers legitimately record a different time location).
- Strong- and weak-site species sums do not exceed their respective master
  capacities beyond the documented floating-point tolerance.
- Parse every clipping report.  No call may exceed the configured
  `maxRelativeClippedMass = 1e-8`; cumulative introduced mass for each element
  must also remain below 0.1% of that element's total supplied mass.

### Element mass balance

Before launch, the production validator must be reviewed and tested to record
time-integrated inlet/outlet advective and diffusive fluxes and aqueous plus
surface inventories for Mn, Mg, and conservative Cl.  For each retained time,

```text
residual = initial inventory + cumulative net boundary input
           - aqueous inventory - surface inventory
```

must be finite and below 1% of `max(|initial + net input|, |final total|)`.
The Cl residual is the nonreactive transport control.  Missing boundary-flux
history is not a mass-balance pass.

### Provenance and figures

- Produce a fail-closed manifest binding paper commit/tree, final runtime and
  PHREEQCRM commits/trees, solver and linked-library hashes, compiler/OpenFOAM
  identity, source image and chemistry hashes, decomposition, every realised
  stage dictionary, logs, checkpoints, fields, validators, and rendered files.
- Verify the manifest from a clean checkout and an archive without relying on
  absolute pilot paths.  Preserve checkpoint and field hashes before any
  reconstruction or curation.
- After the `Surf_*` wrapper mismatch is fixed, regenerate both Kelvin figures
  from times 0/120 and 0/12/.../120.  Open and inspect the rendered figures for
  complete methods/fields, geometry, scales, labels, legends, and visible
  scientific comparison before adding Kelvin result claims to the manuscript.

## Explicit no-launch conditions

Do not launch production if any of these is true:

- PR 6, PR 7, or PR 53 is unreviewed/unmerged, the submodule is not fetchable
  normally, or the final commit gate has not passed at the exact pin;
- the production runtime is dirty, differs from the accepted convergence
  runtime, or lacks complete binary/library provenance;
- the final matched timestep comparison is absent or fails;
- the tracked Kelvin case still differs from the pilot-tested `Surf_*` bundle,
  contains untracked input, or the renderer still requests HFO-prefixed files;
- the 32/64 benchmark, memory measurement, rank decision, or rank-invariance
  check is absent;
- recomputed free disk is below `base + 14 x max(checkpoint size) + 25%`;
- the staged control dictionaries, checkpoint validator, provenance recorder,
  or boundary-flux/mass validator is absent or unreviewed;
- stale, partial, or mismatched checkpoint files are present in the fresh
  production case; or
- the requested execution location is not the local host.

## Measurement records

The completed candidate pilot is bound by manifest SHA-256
`a4cc4bbdb9d687908cd1fc58ec4e1a02d2a03332272c62adb49a920b871d38d0`,
solver-log SHA-256
`f8e339b07e7eff8da19cb97df8b72c0d0c5afaeb57e0935e747a8b700ce06fbd`,
and detached-log SHA-256
`2f499968aa7be777d55f1f7306243748b6e32398c5d4ef8cfe516e385b2af24c`.
The adjacent-comparison artifact records source-manifest hashes
`eb38e0ef928b1a8c5fb20aa152dec211ecb2510d4875bb72e9070a1ed8570abe`
and `a4cc4bbdb9d687908cd1fc58ec4e1a02d2a03332272c62adb49a920b871d38d0`.
These records support the measurements above; they are not substitutes for
the required final-runtime acceptance artifacts.
