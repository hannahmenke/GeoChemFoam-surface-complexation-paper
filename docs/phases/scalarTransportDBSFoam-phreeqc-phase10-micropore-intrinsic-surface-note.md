# Phase 10 Note: Intrinsic Micropore Surface Area

## Why This Change Was Needed

The earlier image-based DBS surface setup used only the interface-count
`aSurf` built by `createASurfPhases.py`. That construction counts phase-label
transitions, so it only creates reactive area near the boundary between the
selected phase and the surrounding phase(s).

For microporous images such as the Kelvin cell, that means:

- adsorption occurred at the pore/micropore boundary,
- but not within the interior of the microporous continuum,
- even though the micropore phase is itself intended to represent unresolved
  porous material with internal reactive surface area.

That behavior was not physically appropriate for the intended model.

## Implemented Fix

`createASurfPhases.py` now supports an additive intrinsic volumetric surface
term:

- `aSurf_total = aSurf_interface + aSurf_intrinsic`

where:

- `aSurf_interface` is the existing phase-boundary term,
- `aSurf_intrinsic` is a phase-fraction-weighted bulk contribution assigned to
  selected labels.

The new optional call signature is:

- `createASurfPhases.py ... fieldName phaseLabels phaseDensities`

with:

- `phaseLabels`:
  - comma-separated image labels that should carry intrinsic surface area
- `phaseDensities`:
  - comma-separated intrinsic surface densities in `[1/m]`, matched
    positionally to `phaseLabels`

Within each coarse cell, the script adds:

- `sum(volume_fraction_of_label * intrinsic_density_of_label)`

to the interface term.

## First Use In The Kelvin Draft Case

The Kelvin draft case now uses:

- intrinsic phase:
  - label `2` (`micropore`)
- draft intrinsic density:
  - `1e5 1/m`

This is a deliberate draft paper value, chosen as a conservative first-pass
order of magnitude aligned with the existing 1D benchmark scale. It is not yet
claimed as a calibrated physical property.

## Verified Effect

After the change, the Kelvin draft initialization reports:

- `sum(aSurf*V)=2.2029360000000006e-04`

and the created `aSurf` field is materially nonzero inside the coarse 3D
micropore volume rather than being concentrated only at the pore/micropore
boundary.

## 8-Rank Kelvin Validation

The fix was then exercised on the full draft Kelvin 3D reactive case:

- tutorial:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`
- command:
  - `conda run -n gcfoam bash -lc './deleteAll.sh && ./runAll.sh'`
- MPI decomposition:
  - `8` ranks (`2 x 2 x 2`)
- reactive log:
  - `reactiveTransportDBSFoamRT.out`

The run completed cleanly to:

- `Time = 400`

with:

- `PhreeqcRM chemistry timing summary: calls=80, total_s=52.696675, avg_s=0.65870844, max_s=1.0969561, last_s=0.64991482`
- total solver runtime:
  - about `63 s` wall clock

The processor-local final fields confirm that the intrinsic micropore surface
term is active throughout the microporous continuum:

- in `processor0/400`, cells with `eps < 1` (`4704` cells) have:
  - `aSurf_nonzero_frac = 1.0`
  - `Surf_aCa+_nonzero_frac = 1.0`
- the pure micropore subset with `eps = 0.4` (`2301` cells) has:
  - `aSurf_nonzero_frac = 1.0`
  - `Surf_aCa+_nonzero_frac = 1.0`
  - `aSurf_mean = 100459.37907431551`
  - `Surf_aCa+_mean = 9.061156671056062e-15`

By contrast, the full-pore cells (`eps = 1`) remain mostly interface-only:

- `10921` cells
- `aSurf_nonzero_frac = 0.03516161523669994`
- `Surf_aCa+_nonzero_frac = 0.03516161523669994`

This is the intended behavior for the new model:

- the macropore phase still carries mostly interface surface area,
- the micropore phase now carries intrinsic internal surface area and therefore
  supports surface complexation throughout its volume.

## Remaining Limitation

The intrinsic micropore surface density is now a required modeling input for
microporous image cases. It is configurable, but it is not derivable from the
segmented image alone. For the paper, this value must be presented as a case
parameter unless a separate calibration path is added.
