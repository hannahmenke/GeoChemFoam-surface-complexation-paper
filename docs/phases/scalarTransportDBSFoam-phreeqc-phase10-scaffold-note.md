# Phase 10 Scaffold Note: Manuscript Workspace

## Scope

This note records the first paper-drafting scaffold for the DBS PHREEQC
surface-complexation work.

## Manuscript Workspace

The paper workspace is:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation`

It currently contains:

- a top-level LaTeX entry file:
  - `main.tex`
- section files:
  - `sections/01_abstract.tex`
  - `sections/02_introduction.tex`
  - `sections/03_model_description.tex`
  - `sections/04_numerical_implementation.tex`
  - `sections/05_validation.tex`
  - `sections/06_test_cases.tex`
  - `sections/07_conclusions.tex`
- a PNG staging location:
  - `figures/png`
- a case/asset map:
  - `cases/README.md`
- a build helper:
  - `build.sh`

## Structure Decision

The manuscript follows the same broad publication logic as the 2021
GeoChemFoam reactive transport paper:

1. Abstract
2. Introduction
3. Model Description
4. Numerical Implementation
5. Validation
6. Test Cases
7. Conclusions

## Test-Case Asset Decision

The paper reuses existing repository image assets for the geometry-driven
sections:

- 2D:
  - `images/raw/4StraightFractures.raw.tar.gz`
- simple 3D:
  - `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- large 3D porous media:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`

## Status

This is a drafting scaffold only. The manuscript now has real mathematical and
implementation prose, but the figure outputs and full test-case result sections
are still provisional.
