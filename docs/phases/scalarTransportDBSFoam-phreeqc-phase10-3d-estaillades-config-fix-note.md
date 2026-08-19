# Phase 10 Note: Estaillades 3D Case Configuration Fix

## Scope

This note records the correction of the large 3D paper case:

- `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesSurfaceComplexation`

## Problem

The original draft case was an accidental copy of the Kelvin setup:

- `createMesh.sh` still pointed at `Kelvin1-200x200x200`
- the image dimensions, labels, porosity mapping, and resolution were all for
  the Kelvin case
- the existing draft outputs were therefore not valid Estaillades results

## Fix Applied

The large 3D case is now configured for the correct source asset:

- image:
  - `Est_3phase500cubed4micron`
- dimensions:
  - `500 x 500 x 500`
- resolution:
  - `4e-6 m`
- labels:
  - `1 = pore`
  - `2 = micropore`
  - `3 = solid`
- phase porosity mapping:
  - `1 -> 1.0`
  - `2 -> 0.4`
  - `3 -> 1.0e-4`

The DBS surface construction for the reactive stage is also corrected:

- `createASurfPhases.py` now uses:
  - `pad_value = 1`
  - `solid_value = 3`
  - intrinsic micropore surface on label `2`

## Immediate Consequence

Any older `3DEstailladesSurfaceComplexation` reactive outputs generated before
this fix must be treated as invalid for the paper. The case has to be rerun
from the corrected configuration before any 3D Estaillades concentration or
surface-loading figure is accepted.
