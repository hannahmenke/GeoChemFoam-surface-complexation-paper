# 3D external surface-area validation

This case isolates the external pore-solid surface area in a real three-dimensional Estaillades image crop. The micropore phase is remapped from label `2` to the solid label `3`, so the comparison includes only the pore-solid interface and excludes intrinsic micropore surface area.

The validation is area-only: it does not run flow, transport, or PHREEQC chemistry. The purpose is to compare the conventional DBS staircase surface measure against the `smoothSurface` interface reconstruction on the same Cartesian image support.

## Source image

- image: `Est_3phase500cubed4micron`
- source label convention: pore `1`, micropore `2`, solid `3`
- validation remap: micropore `2 -> 3`
- voxel size: `4e-6 m`
- default crop origin: `(x, y, z) = (300, 340, 40)`
- default crop size: `128 x 128 x 128`
- metric support: one cell layer is excluded from each crop boundary to avoid measuring artificial crop-box surfaces

The source image is read from `$GCFOAM_IMG`, `images`, or `images/raw`.

## Outputs

- `results/area_metrics.csv`
- `results/area_metrics.json`
- `../../figures/png/fig11_3d_external_surface_area_validation.png`

Regenerate the full case from this directory with:

```bash
cd papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_external_surface_area_validation
./runAll.sh
```

The paper figure renderer delegates to this case-level `runAll.sh` so the metrics and figure share the same reproducible entry point.

The case-local analyzer is:

- `scripts/generate_3d_external_surface_area_validation.py`
