# 1D Analytical Manuscript Case

## Source

- paper-local executable case:
  - `cases/1d_linear_retardation`
- reproducible entry point:
  - `runPhase8AnalyticalBenchmark.sh`
  - `runConvergenceStudy.sh` for the mesh- and timestep-refinement study
- runtime selection:
  - set `GCFOAM_RUNTIME_ROOT` to a clean, isolated GeoChemFoam checkout

## Paper Role

- analytical validation
- dilute linear-equilibrium benchmark
- calibration of the field-level retardation factor

## Required Outputs

- aqueous concentration profile
- analytical comparison profile
- surface-loading profile
- one summary metric table row
- mesh- and timestep-refinement metrics in `convergence_results.json` and
  `convergence_results.csv`

## Planned Figure

- `figures/png/fig01_1d_retardation.png`
  - left panel: normalized aqueous Ca$^{2+}$ profile vs analytical reference
  - right panel: normalized `Surf_aCa+` profile vs linear-limit reference
- `figures/png/fig06_1d_breakthrough.png`
  - outlet breakthrough curves for aqueous-only and surface-enabled runs

Regenerate both figures after a completed run with:

```bash
../../figures/scripts/render_1d_validation_figures.sh
```
