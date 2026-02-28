# 2D Manuscript Case: 4StraightFractures

## Source Asset

- image:
  - `images/raw/4StraightFractures.raw.tar.gz`
- metadata:
  - `images/raw/4StraightFractures.txt`

## Paper Role

- simplest image-based geometry
- visually transparent 2D retardation and uptake case

## Source Metadata

- image size:
  - `500 x 500 x 1`
- segmentation:
  - `phases`
- labels:
  - `1 = matrix`
  - `2 = pore`
- note:
  - the source metadata reserves `0 = solid`, but the raw image itself uses
    only labels `1` and `2`
  - the manuscript draft currently treats label `1` as the reactive
    solid-like matrix phase for `aSurf`
  - the source metadata does not currently report a resolved voxel size

## Runtime Case

- solver case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/4StraightFracturesSurfaceComplexation`
- draft mesh:
  - `250 x 250 x 1`
- production draft run:
  - `8` MPI ranks (`4 x 2 x 1`)

## Current Outputs

- geometry panel
- aqueous concentration panel
- surface-loading panel

## Figure

- `figures/png/fig02_2d_fractures.png`
  - populated from the `t = 2000` solver output
