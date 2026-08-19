# Phase 10 Note: Image-Case Baseline Definition

## Scope

This note records the shared draft setup for the image-based manuscript cases.

## Shared Draft Physics

Unless a section explicitly states otherwise, the 2D and 3D manuscript cases
should use:

- solver:
  - `reactiveTransportDBSFoam`
- chemistry:
  - the same dilute calcium surface-complexation system used in the 1D
    analytical benchmark
- transport species:
  - `Ca+2`
  - `Cl-`
  - `H+`
  - `OH-`
- surface species:
  - `Surf_a-`
  - `Surf_aCa+`
  - `Surf_aH`

## Shared Draft Boundary / Initial Conditions

- flow direction:
  - left to right
- inlet chemistry:
  - dilute `CaCl2` pulse / step with the same order of magnitude used in the
    1D benchmark
- initial aqueous state:
  - zero dissolved calcium and chloride
  - background `H+` / `OH-`
- initial surface state:
  - PHREEQC-initialized equilibrium surface

## Shared Draft Outputs

Each image-based case should report at least:

- one geometry panel
- one aqueous calcium panel
- one surface-loading panel (`Surf_aCa+`)
- one integrated metric:
  - outlet breakthrough, mean dissolved calcium, or total adsorbed calcium

## Status

This is a draft baseline for manuscript consistency. It still needs to be
realized as fully reproducible 2D and 3D solver cases.
