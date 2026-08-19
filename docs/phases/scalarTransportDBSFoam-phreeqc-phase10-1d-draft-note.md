# Phase 10 Note: 1D Validation Draft Section

## Scope

This note records the first non-placeholder manuscript result in the Phase 10
paper track.

## What Was Added

The validation section in:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/sections/05_validation.tex`

now includes:

- the measured 1D analytical benchmark values,
- an explicit statement of the validated field-level retardation agreement,
- a corrected cell-averaged advection-diffusion comparison in place of the
  earlier sharp-step overlay,
- the first real manuscript figure instead of a placeholder box.

## Figure

The first staged paper PNG is:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig01_1d_retardation.png`

It is generated from the tracked 1D benchmark case using:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_1d_retardation_plot.py`

## Status

The 1D analytical section is now the first paper section with a real plotted
result. The current 1D figure now compares the aqueous-only and
surface-enabled numerical cell averages against their matching cell-averaged
analytical profiles, which makes the comparison materially more honest for a
finite-volume plot. The 2D, simple 3D, and large 3D Estaillades-style sections
still need their actual figure outputs.
