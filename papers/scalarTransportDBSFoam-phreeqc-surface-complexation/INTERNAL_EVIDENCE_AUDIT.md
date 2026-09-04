# Internal evidence audit for TPM length refactor

This file is not manuscript content and is excluded from the submission export.

Last reviewed 2026-09-04. The entries below describe the manuscript as it
currently stands on this branch, not the reduced state of the 2026-08-30
length refactor.

## Current state

- The full Pe=0.1 to 10 resolved-to-DBS sweep, its aggregate metrics, and its
  conclusion claims were removed on 2026-08-30 (`d51d0d9`) and restored on
  2026-09-03 by `00c4c5a`, "Restore complete agreed manuscript structure".
  The sweep is reported in `sections/05_validation.tex` and its results are
  carried into `sections/07_discussion.tex` and `sections/08_conclusions.tex`.
- Two-scale figures now used in the manuscript:
  `fig09_two_scale_error_vs_peclet.png`, `fig10_two_scale_pe1_fields.png`,
  and `fig12_two_scale_lithium_nested_geometries.png`.
  `fig13_two_scale_lithium_sorption_validation.png` is retained in the
  repository and is not referenced by either document.
- Kelvin is presented in `sections/06_test_cases.tex` as an application case
  with `fig03_3d_kelvin.png` and `fig07_kelvin_temporal.png`. The production
  rerun is in progress; `cases/3d_kelvin/` holds the README and preflight only,
  and the runnable case is at
  `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`
  (2x4x4, 32 ranks).

## Open provenance gap

`figures/accepted_nonkelvin_provenance.json` binds figures 01, 02, 04, 06 and
08 only, and `validate_accepted_nonkelvin_artifacts.sh` checks that set. The
restored two-scale figures (09, 10, 12) and the Kelvin figures (03, 07) are
bound by no manifest, so `build.sh` does not verify the data behind claims the
manuscript now makes. Either extend the accepted contract to cover them or
record why they sit outside it.

## Unresolved numerical items

- Closed-batch relative inventory drifts are reported as 8.9e-10 and 1.1e-10
  in `sections/05_validation.tex` and the supplementary. Recomputing the
  combined inventory from the committed `cases/1d_linear_retardation/
  phase8_batch_secant.out` gives roughly 2.4e-8 and 1.1e-8. The pre-chemistry
  baseline `Surf_aCa+` field is not committed, so the discrepancy is not
  resolved either way. To be investigated.
- The controlled circular-post and sphere benchmarks report smoothSurface
  errors (0.2%, and -0.06%/+0.87% at R/dx = 8 and 16) for which no
  smoothSurface data is committed:
  `cases/2d_circular_post_surface_area_benchmark/results/area_metrics.csv`
  contains snappy rows only, and `cases/3d_sphere_surface_area_benchmark/`
  has no `results/` directory. To be investigated.
