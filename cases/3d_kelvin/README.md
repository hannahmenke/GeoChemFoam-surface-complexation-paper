# 3D Manuscript Case: Kelvin Cell

## Source Asset

- image:
  - `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- metadata:
  - `images/raw/Kelvin1-200x200x200.txt`

## Paper Role

- controlled 3D geometry
- first 3D demonstration of topology-driven unresolved surface interaction

## Source Metadata

- image size:
  - `200 x 200 x 200`
- voxel size:
  - `10 mum`
- labels:
  - `1 = pore`
  - `2 = micropore` (paper rendering convention)

## Current Draft Surface Model

- the Kelvin draft case now uses:
  - interface-count `aSurf`
  - plus an intrinsic micropore contribution inside label `2`
- current draft intrinsic micropore density:
  - `1e5 1/m`
- this is a case parameter, not yet a calibrated physical claim

## Planned Outputs

- aqueous concentration volume render
- surface-loading volume render

## Planned Figure

- `figures/png/fig03_3d_kelvin.png`

## Current Draft Figure Convention

- the current draft figure is a true 3D volume render of the stitched solver
  fields
- both panels use the same camera
- the left panel shows dissolved `Ca+2`
- the right panel shows adsorbed `Surf_aCa+`
- per-panel relative scaling is used to emphasize spatial structure
