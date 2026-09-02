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

## Resolved canonical case integration

### Historical base-case integration gap

**Measured at base commit `019f7e4c`:** the executable Kelvin case was
`tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`.
The paper `cases/3d_kelvin` directory contains documentation, not a second case
copy.  At that base commit, the tracked tutorial used HFO-prefixed surface-field
names, whereas all completed pilots used the project `Surf_*` convention.  The
base-commit figure wrapper requested HFO-prefixed fields in both its
`required_fields` list and renderer arguments; the pilots wrote
`Surf_sOMn+`, `Surf_wOMn+`, and `Surf_wOMg+`.

Nine logical tracked inputs differ; the first row comprises both the template
and realised dictionary, so ten file paths differ.  The pilot manifest recorded
the first seven rows but omitted the two orchestrating scripts in the final two
rows.  `Reviewed` is the canonical tutorial at base commit `019f7e4c`; `Pilot` is the
preserved completed paper-case copy from which the measurements were made:

| Canonical relative input | Reviewed SHA-256 | Pilot SHA-256 | Material difference |
|---|---:|---:|---|
| `constant/thermoPhysicalProperties{,1}` | `ff8793b418b15cf3874a9c169f6b910a807ad875b81cc382403ebb4228e5694c` | `91b7d1229e4d3758000b7069486cc791a6ae5a5ca4e3375677f21201e81cee77` | HFO-prefixed fields/masters versus `Surf_*` |
| `constant/phreeqcReactions` | `ff378541ec4ee4ab6ad5603aa5724c632a9f73b1438cdd79a67d74126a463e62` | `fae65265504bb6166ee72ed69b78f995cbee6c5f9a9d6055d07dadef19912a76` | matching PHREEQC names and selected output |
| `system/controlDict1` | `d451ebc96ab88ff10f10245a00220782041283df45c74df4a542c76f8e12f276` | `79c401347771ab95e4859bcb8c4b855a9417c562230cf690adc57e5542253335` | explicit restore switch |
| `system/fvSolution1` | `7d5613e3664a04c736614e991acb75f027ddfa4a36aac80d6acd1e7d01d421aa` | `40e0c0c721d360ed8217479cb8f30632c020b95fc7e852a423d5c25e7d6d2392` | tighter scalar solve and zero relative tolerance |
| `runCaseFlow.sh` | `956e144256256a2db00cd69985cc31ee09f38b5e3c3a46e35e5028919a263260` | `cb8c11f671bf16974850132d3741747bca9a21389dd034eee2769447b2aad830` | explicit flow-duration override |
| `initCaseReactiveTransport.sh` | `ea2a9b7a174ea23fafe1e0d81ea542463aafb401e8c379300f0d011e92b39080` | `abd6bb498e9cf35f931611ecbc534657e90ac3ddb2f66e3fd4e29e7fe25208ec` | runtime isolation, provenance, and `Surf_*` fields |
| `runCaseReactiveTransport.sh` | `2a2f589d41a7c19a6bc56caa76d74505b21105b1da5572f686a81d615175ed2e` | `962fade27bac9567c09cfb1cee27d957aa13411fcd1885313102004e9fc01721` | runtime isolation, pilot timestep, and run manifest |
| `runAll.sh` | `1c9d9c0e8b8532f4dd81b723987a45834a87c70589bd8fa9cd344ddf81c5db07` | `897746015273b2b7620964aa272f68d719999b240799f3d5c3c457be5e9559ff` | paper runtime configuration and selected-runtime logging |
| `deleteReactiveTransport.sh` | `4dd4999413df2a3fab6b72dde113e9f1a08792f637deed63f077863fa115817b` | `ea8ef45b9339dead1218f34fbce97ace0b97bceeebca20a3e568aeed1943d92e` | provenance cleanup and `Surf_*` field/master names |

The pilot `kelvin_provenance.py` was also absent from that base tree, and the
pilot cases contained untracked realised inputs and outputs.

**Current canonical integration:** the tracked head resolves this historical
gap as one coherent case change.  The following are invariants that must remain
true for acceptance and production:

1. The tracked tutorial above is the single canonical source and production
   bundle; `papers/.../cases/3d_kelvin` remains documentation-only.  It contains
   the reviewed nine logical input changes and `kelvin_provenance.py`.
2. Keep `configure_runtime.sh` at
   `papers/.../cases/configure_runtime.sh`.  Resolve it from the repository root
   in every tutorial script and detached command; do not rely on a case-relative
   `../configure_runtime.sh` path.
3. The wrapper's `required_fields` and renderer arguments use the tracked
   `Surf_*` names.  The Python
   renderers already accept field names as arguments; do not add ion-name or
   surface-name special cases to solver or adapter code.
4. Regenerate each clean tutorial case from the accepted commit and prove its manifest
   covers all ten tracked paths, `kelvin_provenance.py`, chemistry, geometry,
   decomposed initial fields, runtime, solver, and linked libraries.  No local
   patch or untracked input may remain.

## Timestep-convergence gate

The 32-rank pilots used identical 200 x 200 x 200 meshes, a 2 x 4 x 4
decomposition, a 0.5 s endpoint, and one matched checkpoint.  Completed-run
measurements are:

| `deltaT` [s] | Detached wall [s] | Final solver clock, including endpoint I/O [s] | mean Co | max Co | status | checkpoint pairs |
|---:|---:|---:|---:|---:|---:|---:|
| 0.0015625 | 6,808 | 6,799 | 0.0581960 | 0.201417 | 0 | 32/32 |
| 0.00078125 | 13,544 | 13,535 | 0.0290980 | 0.100709 | 0 | 32/32 |
| 0.000390625 | 26,131 | 26,121 | 0.0145490 | 0.0503543 | 0 | 32/32 |

The independently reproduced completed comparison `0.0015625` versus
`0.00078125` did not pass: sorbed-Mn global relative L1 difference was
7.560231%, sorbed-Mn inventory differed by 1.581806%, and aqueous-Mn relative
L1 difference was 0.363160%; all recorded front shifts were zero.  Therefore
the completed comparison does not establish `0.00078125` as a production
timestep.

The more relevant completed comparison `0.00078125` versus `0.000390625` also
did not pass.  Sorbed-Mn global relative L1 difference was 4.147294%, while
aqueous-Mn relative L1 was 0.185760%.  Aqueous, sorbed, and total Mn inventory
differences were 0.066285%, 0.842758%, and 0.232488%, respectively.  The
sorbed-Mn 90th-percentile front shifted by one 10 micrometre cell; the other
front criteria passed.  Thus only the below-1% distribution criterion failed.
Both inputs had 32/32 valid checkpoint pairs and 1,048 validated provenance
records each.

**Required:** after the final runtime and tracked `Surf_*` case exist, run the
matched `0.000390625`/`0.0001953125` pair again on that exact identity.  The
comparison artifact must validate every recorded hash, all 32 checkpoint
pairs, identical mesh/initial fields/chemistry, and all of these criteria:

- each aqueous, sorbed, and total Mn inventory difference is below 1%;
- global relative L1 differences for aqueous and sorbed Mn are below 1%;
- Mn front positions at the 10th, 50th, and 90th inventory percentiles differ
  by no more than one 10 micrometre cell and by less than 1% of domain length;
- all values are finite and every field that is analytically nonnegative is at
  least `-1e-12` in its native units; record the minimum and count of values
  below zero rather than silently clipping them in the comparator.

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
unsplit solver clock for 0.5 s simulated time.  The preceding 26,085 s log
entry is at simulated time 0.499609375 s, not at 0.5 s before checkpoint I/O;
the remaining 36 s includes the final transport/reaction step as well as final
field/checkpoint publication and cannot be assigned to checkpoint writing.
Compute, write, restore, and staged-startup costs have not been measured as
non-overlapping components.

**Derived provisional unsplit baseline:**

```text
Tunsplit,120,32 = 26,121 s x (120 / 0.5) = 6,269,040 s
                 = 1,741.4 h = 72.5583 d
```

This is only linear scaling of one whole-case measurement: it is neither a
component model nor a production forecast, because it repeats the endpoint
overhead at the wrong frequency and contains no restores or staged launches.
Instrument the rank benchmark and restart-equivalence test to measure mutually
exclusive `Tcompute,120,32`, `Twrite,R`, `Trestore,R`, and aggregate
`Tstartup,total,R`.  Then project

```text
T120,R = Tcompute,120,32 / Scompute,R + 14 x Twrite,R
         + 13 x Trestore,R + Tstartup,total,R
```

Only the compute term is divided by the measured 32-to-64 compute speedup; add
each measured I/O or startup component exactly once, then apply the **assumed**
10% contingency to the full sum.  Do not advertise a 32- or 64-rank duration
before those measurements.

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
data, time 0, and other non-endpoint case content occupy 3,210,031,104 allocated
bytes.  The completed case
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
same sizes and finite extrema.  Compare every aqueous field value using
`abs(a-b) <= 5e-18 kmol m^-3 + 5e-3*max(abs(a),abs(b))` and every non-static
surface field value using
`abs(a-b) <= 2e-17 kmol m^-2 + 5e-5*max(abs(a),abs(b))`.  Derive the allowable
aqueous/sorbed inventory differences and spatial L1 norms by integrating those
same per-cell bounds with the actual cell-volume, porosity, and surface-area
weights; do not apply a separate unitless tolerance.  Non-chemistry restart
state, boundary structure, and front indices must be identical.  Failure of any
part of this contract is a no-launch result.

Once all gates pass, prepare the first 0-to-1 s stage exactly as follows in the
fresh case (subsequent stages replace start/end/interval and set restore true):

```bash
cd /absolute/path/to/fresh-repository-worktree
export KELVIN_REPO_ROOT=$PWD
cd "$KELVIN_REPO_ROOT/tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation"
export GCFOAM_RUNTIME_ROOT=/absolute/path/to/final-clean-runtime
export KELVIN_EXPECTED_GCFOAM_COMMIT=/reviewed/GeoChemFoam/commit
export KELVIN_EXPECTED_GCFOAM_TREE=/reviewed/GeoChemFoam/tree
export KELVIN_EXPECTED_PHREEQCRM_GITLINK=/reviewed/superproject/gitlink
export KELVIN_EXPECTED_PHREEQCRM_COMMIT=/reviewed/PHREEQCRM/commit
export KELVIN_EXPECTED_PHREEQCRM_TREE=/reviewed/PHREEQCRM/tree
source "$KELVIN_REPO_ROOT/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/configure_runtime.sh"
cp system/controlDict1 system/controlDict
cp system/fvSolution1 system/fvSolution
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
  "$KELVIN_REPO_ROOT/tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation" \
  'source "$KELVIN_REPO_ROOT/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/configure_runtime.sh"; export FOAM_SIGFPE=false OMP_NUM_THREADS=1 KELVIN_USE_PREPARED_CONTROL=true KELVIN_MPI_ARGS="--bind-to core --map-by core" KELVIN_SOLVER_LOG=reactiveTransportDBSFoamRT_0_to_1.out; bash runCaseReactiveTransport.sh' \
  kelvin_local_0_to_1
```

Use a stage-specific solver-log name and prefix containing start/end times in
the actual launch record.  The helper creates timestamped `.log`, `.pid`, and
`.status` files.  Perform exactly one startup check after two seconds: the
outer log must be nonempty, the recorded PID must exist, and the solver log
must show the intended start time/runtime.  Do not poll thereafter unless
asked.

The case wrapper records the stage as `attempted` before launching.  It changes
that record to `completed` only after a zero solver exit, a clean endpoint in
the solver log, and valid endpoint fields and checkpoint pairs on every rank.
An interrupted attempt therefore remains explicit and may only be retried from
its recorded authoritative start with the identical interval and controls.  A
normal continuation must start at the last completed endpoint.  Intermediate
outputs from an interrupted attempt are not authenticated restart states.

At stage completion, require status 0, solver `End`, the intended endpoint,
and on every rank:

- `phreeqc.dmp` and `phreeqc.complete` both exist;
- no `phreeqc.complete.tmp` or other checkpoint temporary remains; and
- the marker magic, time, dump size, and dump SHA-256 all validate.

On a crash, preserve and hash the logs and incomplete artifacts first.  Retry
the exact attempted interval from its recorded start state with the identical
runtime, inputs, timestep, rank count, and decomposition.  Quarantine every
later incomplete or intermediate directory outside the retry copy.  Do not
promote it to a restart state, even if it contains a self-consistent marker and
dump.  If the intended endpoint and clean solver log are both complete, rerun
the provenance finalisation check instead of creating a different stage.

## Production acceptance

Production is evidence only after all of the following pass.

### Completion and chemistry

- All fourteen stages have status 0, clean `End`, exact endpoints, and valid
  checkpoint pairs on every rank; no fatal, floating-point, or PHREEQC error is
  present.
- Every aqueous and surface field is finite; every field that is analytically
  nonnegative is at least `-1e-12` in its native units.  Record each field's
  minimum and count below zero, with no silent validator clipping.  The
  numerical internal and boundary values of `eps` and both surface-area fields
  match their initial values at every checkpoint (file headers legitimately
  record a different time location).
- Strong- and weak-site species sums do not exceed their respective master
  capacities beyond the documented floating-point tolerance.
- Parse every clipping report.  No call may exceed the configured
  `maxRelativeClippedMass = 1e-8`; cumulative introduced mass for each element
  must also remain below 0.1% of that element's total supplied mass.

### Element mass balance

Before launch, the production validator must be reviewed and tested against
these explicit units and signs.  Aqueous concentration `C` is in kmol m^-3
(numerically mol L^-1), surface concentration `Gamma` is in kmol m^-2,
`aSurf` is the chemistry-supplied interfacial area density in m^-1, cell volume
`V` is in m^3, `eps` is dimensionless, and outward-oriented face flux `phi` is
in m^3 s^-1.  Do not treat `Gamma` as an intrinsic volumetric concentration.
At each retained time calculate, in kmol,

```text
C_Mn = field Mn+2; C_Mg = field Mg+2; C_Cl = field Cl-
N_X,aqueous = sum_cells eps_i C_X,i V_i
N_Mn,surface = sum_cells aSurf_i
               (Gamma_Surf_sOMn+,i + Gamma_Surf_wOMn+,i) V_i
N_Mg,surface = sum_cells aSurf_i Gamma_Surf_wOMg+,i V_i
N_Cl,surface = 0
```

Use the mesh cell volumes rather than assuming a uniform voxel volume.  Site
capacity checks must use the same `aSurf * Gamma * V` conversion and enumerate
the species actually included; an observed-species sum is not a full-site
closure unless every site-bearing species is recorded.

For each boundary face, define outward-positive fluxes in kmol s^-1:

```text
Fadv,out,X  = sum_faces phi_f C_X,f
Fdiff,out,X = -sum_faces [(eps D_X)_f grad(C_X)_f dot S_f]
Fin,X       = -(Fadv,out,X + Fdiff,out,X)
```

Use the tensor form when `D_X` is tensorial, and the solver's interpolation and
discretisation (or solver-recorded face fluxes) so validator reconstruction
does not introduce a different scheme.  Integrate `Fin,X` over solver timesteps
with a documented quadrature to obtain cumulative net input in kmol.  For each
retained time,

```text
residual_X = initial total inventory_X + integral(Fin,X dt)
             - final total inventory_X
```

where total Mn and Mg include the mapped aqueous and surface terms above and
total Cl is aqueous only.  The residual must be finite and below 1% of
`max(|initial + net input|, |final total|)`.  The Cl residual is the
nonreactive transport control.  Missing boundary-flux history or undocumented
signs/units is not a mass-balance pass.

### Provenance and figures

- Produce a fail-closed manifest binding paper commit/tree, final runtime and
  PHREEQCRM commits/trees, solver and linked-library hashes, compiler/OpenFOAM
  identity, source image and chemistry hashes, decomposition, every realised
  stage dictionary, logs, checkpoints, fields, validators, and rendered files.
- Verify the manifest from a clean checkout and an archive without relying on
  absolute pilot paths.  Preserve checkpoint and field hashes before any
  reconstruction or curation.
- Using the integrated `Surf_*` wrapper, regenerate the spatial and temporal
  Kelvin figures from times 0/120 and 0/12/.../120.  They must show
  the Mn/Mg competition in both aqueous and surface fields.  Open and inspect
  them for complete fields, geometry, scales, labels, legends, and visible
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
The `0.0015625`/`0.00078125` comparison artifact has SHA-256
`bdad624a8ee1960e3ed06974d83566391cf718b4bc2ac62e5991fd240453fb34`;
the independent reimplementation has SHA-256
`a7f981390c8152257f3c01faf6b21fc4874e71c34c2926267d4166707fce370a`,
and the pair-identification diagnosis has SHA-256
`b18d8955e75949a5794421c5a5eaba2391f6689532f01526ca27ea467375b1bc`.
The `0.00078125`/`0.000390625` artifact has SHA-256
`b839316e8441e9394f426fbce6249eeb7d98c37d2c61253c5736e79797a07140`
and was generated by comparator commit
`46317fcac609819c35e1a85b1de6a3c73a6d156f` from source manifests
`eb38e0ef928b1a8c5fb20aa152dec211ecb2510d4875bb72e9070a1ed8570abe`
and `a4cc4bbdb9d687908cd1fc58ec4e1a02d2a03332272c62adb49a920b871d38d0`.
These records support the measurements above; they are not substitutes for the
required final-runtime acceptance artifacts.
