# HM12 Four-Case Solver Comparison

This benchmark freezes the full-resolution HM12 comparison used for the paper figure into a repo-native case set.

Subcases:
- `legacy-snappy`: resolved-wall `reactiveScalarTransportFoam` on the connected HM12 mask with `snappyHexMesh`
- `legacy-subset`: resolved-wall `reactiveScalarTransportFoam` on the connected HM12 mask with `subsetMesh`
- `dbs-file`: `reactiveScalarTransportDBSFoam` using the explicit file-based `aSurf`
- `dbs-fallback`: `reactiveScalarTransportDBSFoam` using solver-generated fallback `aSurf`

Frozen comparison settings:
- HM12 crop: `x=700:1300`, `y=700:1300`, `z=1:2`
- Connected pore mask: `HM12_2_4_thr120_conn`
- Mesh: `600 x 600 x 1`
- Pressure-driven flow
- Reactive end time: `t = 200 s`
- DBS solid floor: `1e-8`
- DBS chemistry cutoff: `thetaChemistryMin = 1e-3`
- DBS momentum mode: `stokesDBS = true`

How to run:
```bash
cd tutorials/reactiveTransport/HM12SurfaceComplexationSolverComparison
./runAll.sh
```

What `runAll.sh` does:
- runs the four subcases in sequence
- renders the paper figure with the paper-facing plotting script

Figure output:
- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/hm12_fourcase_solver_comparison_t200.png`

Notes:
- The fallback case is self-contained here: its `runAll.sh` removes `0/aSurf` and `processor*/0/aSurf` before the reactive solve, so no external wrapper is needed.
- The plotting script used by this benchmark lives in:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_hm12_fourcase_conc_sorbed_diff.py`
- The legacy sorbed fields are plotted from wall-face values (`fixedWalls` / `walls`), not from the zero-valued cell `internalField`.
