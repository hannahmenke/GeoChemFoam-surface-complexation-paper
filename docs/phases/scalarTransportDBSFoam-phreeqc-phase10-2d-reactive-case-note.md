# Phase 10 Note: 2D Reactive Fracture Case

## Scope

This note records the first image-based 2D manuscript case built for the paper:

- runtime case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/4StraightFracturesSurfaceComplexation`
- figure:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig02_2d_fractures.png`

## Case Definition

- source image:
  - `images/raw/4StraightFractures.raw.tar.gz`
- raw labels present in the image:
  - `1 = matrix`
  - `2 = pore`
- important detail:
  - the metadata reserves `0 = solid`, but this particular image contains no
    voxels with label `0`
- draft runtime mesh:
  - `250 x 250 x 1`
- production draft runtime mode:
  - `8` MPI ranks (`4 x 2 x 1`)

## Key Implementation Choice

The first `aSurf` attempt failed because the surface-area builder was told to
treat label `0` as the reactive solid phase, but label `0` does not exist in
this image. The corrected draft case therefore computes `aSurf` using:

- matrix-like reactive phase:
  - label `1`
- non-reactive open phase:
  - label `2`

For this image, that is the correct interpretation of the unresolved internal
reactive interface.

## Commands Run

- `./runAll.sh`
- long rerun after enabling the `8`-rank path:
  - `./deleteAll.sh`
  - `./runAll.sh`
- figure generation:
  - `python papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_2d_raw_geometry.py ... --parallel-case ... --time-name 2000 --npx 4 --npy 2 --time-label 't = 2000 (8 MPI ranks)'`
  - updated paper snapshot from the clean unrestarted run:
    - `python papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_2d_raw_geometry.py ... --parallel-case ... --time-name 3000 --npx 4 --npy 2 --time-label 't = 3000'`

## Observed Results

- first interface-only draft:
  - `createASurfPhases.py` reported:
    - `sum(aSurf*V)=3.0400000000000007e-05`
  - this produced adsorption mainly on the matrix/pore interface and left most
    `eps = 0.4` matrix cells without reactive surface area
- corrected draft with intrinsic micropore surface on label `1`:
  - `createASurfPhases.py` now reports:
    - `sum(aSurf*V)=2.1990400000000004e-02`
  - at `t = 2000`:
    - `Ca+2 max = 1.9999503e-09`
    - in the `eps = 0.4` matrix subset on `processor0/2000`:
      - `aSurf_nonzero_frac = 1.0`
      - `Surf_aCa+_nonzero_frac = 1.0`
      - `aSurf_mean = 100005.59728441427`
      - `Surf_aCa+_mean = 3.0160361038264912e-15`
- the 2D PNG is now a real three-panel results figure:
  - geometry
  - normalized dissolved calcium
  - normalized adsorbed calcium
- the current paper draft uses the later `t = 3000` snapshot so the fracture
  surface loading is more developed
- the `t = 3000` paper snapshot is taken from the clean unrestarted
  `0 \rightarrow 3000` run, not from the rejected restart continuation

## Timing

- solver log:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/4StraightFracturesSurfaceComplexation/reactiveTransportDBSFoamRT.out`
- observed end-of-run wall-clock in the log:
  - about `240 s` to `t = 3000` after adding the intrinsic matrix surface term
- this is a draft paper-case timing on `8` MPI ranks, not the formal benchmark
  harness

## Acceptance

- acceptance criterion for this paper-stage step:
  - the 2D case must produce nonzero `aSurf`, a nonzero `Surf_aCa+` field, and
    a reproducible PNG tied to a concrete runtime case
  - the corrected matrix phase must show `Surf_aCa+` throughout the
    `eps = 0.4` microporous region, not only at the interface
- result:
  - passed

## Remaining Risk

- the 2D section is now materially usable and much more representative than the
  short early-time draft, but it still needs a final narrative pass once the
  3D sections are in place
