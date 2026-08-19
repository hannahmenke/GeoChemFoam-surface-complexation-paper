# Phase 10 Note: Corrected Estaillades 3D Run

## Scope

This note records the first successful corrected production run for:

- `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesSurfaceComplexation`

## What Changed Before The Run

Two fixes were required before the case became usable:

- the case was reconfigured from the accidental Kelvin duplicate to the real
  `Est_3phase500cubed4micron` image
- the reactive initializer now masks `aSurf` to zero for cells with:
  - `theta <= 1e-3`

The second fix prevents PHREEQC from attempting surface complexation in the
near-solid regularization cells.

## Successful Run

The corrected case now completes cleanly to:

- `t = 400`

on:

- `8` MPI ranks

The solver log is:

- `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesSurfaceComplexation/reactiveScalarTransportDBSFoamRT.out`

## Measured Results

Final timing:

- total wall-clock:
  - about `82 s`
- PHREEQC chemistry summary:
  - `calls = 80`
  - `total_s = 58.103041`
  - `avg_s = 0.72628801`

Final stitched field summary:

- `Ca+2`:
  - `min = 7.1261642e-13`
  - `max = 1.9999984e-09`
  - `mean = 1.721298824122949e-09`
- `Surf_aCa+`:
  - `min = 0`
  - `max = 9.0611907e-15`
  - `mean = 6.975891762887509e-15`
- `aSurf`:
  - `mean = 7.65054738e4`
- `theta`:
  - `mean = 0.36085134319600004`

Phase-binned interpretation:

- near-solid (`theta <= 1e-3`):
  - `aSurf_mean = 0`
  - `Surf_aCa+_mean = 0`
- micropore (`0.1 < theta < 0.9`):
  - `Surf_aCa+_mean = 8.434404086095165e-15`
- macropore (`theta >= 0.9`):
  - `Surf_aCa+_mean = 6.93189505867026e-15`

So the corrected masking behaved as intended: adsorption is no longer being
forced into the numerical solid skeleton.

## Manuscript Figure Status

The chemistry run is now valid and the corresponding manuscript 3D field figure
is now generated through the working `gcfoam` EGL volume-render path.

Generated output:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades.png`

Reported manuscript figure time:

- `t = 100`

This earlier written time is used intentionally for the paper figure because
the dissolved front is still close to the half-domain position there, which is
more informative visually than the later near-throughflow state.

That figure is now the active draft result for the large 3D case.
