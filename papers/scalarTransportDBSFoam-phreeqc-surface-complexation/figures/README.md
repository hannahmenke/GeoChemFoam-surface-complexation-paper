# Figure reproduction map

The manuscript uses 14 numbered figures. Historical file prefixes do not always
match the final manuscript number; use this table or
`../reproducibility_manifest.json` rather than inferring numbers from filenames.

| Figure | Published PNG | Simulation/source | Renderer |
|---:|---|---|---|
| 1 | `png/fig01_1d_retardation.png` | `cases/1d_linear_retardation` | `scripts/render_1d_validation_figures.sh` |
| 2 | `png/fig02_2d_fractures.png` | `cases/2d_4StraightFractures` | `scripts/render_2d_fractures_figure.sh` |
| 3 | `png/fig03_3d_kelvin.png` | `tutorials/.../3DKelvinSurfaceComplexation` | `scripts/render_kelvin_mnmg_figures.sh` |
| 4 | `png/fig04_3d_estaillades.png` | `cases/3d_estaillades` | `scripts/render_estaillades_figures.sh` |
| 5 | `png/fig05_solver_workflow.png` | GeoChemFoam solver source | `scripts/generate_solver_workflow.py` |
| 6 | `png/fig06_1d_breakthrough.png` | `cases/1d_linear_retardation` | `scripts/render_1d_validation_figures.sh` |
| 7 | `png/fig07_kelvin_temporal.png` | `tutorials/.../3DKelvinSurfaceComplexation` | `scripts/render_kelvin_mnmg_figures.sh` |
| 8 | `png/fig08_estaillades_temporal.png` | `cases/3d_estaillades` | `scripts/render_estaillades_figures.sh` |
| 9 | `png/fig09_sphere_surface_area_validation.png` | sphere and circular-post benchmarks | `scripts/render_surface_area_validation_figures.sh` |
| 10 | `png/fig10_hm12_surface_area_validation.png` | HM12 resolved-wall and DBS cases | `scripts/render_surface_area_validation_figures.sh` |
| 11 | `png/fig11_3d_external_surface_area_validation.png` | `cases/3d_external_surface_flow_validation` | `scripts/render_3d_external_surface_area_validation.sh` |
| 12 | `png/fig12_two_scale_lithium_nested_geometries.png` | two-scale micromodel case | `scripts/render_two_scale_lithium_sorption_validation.sh` |
| 13 | `png/fig09_two_scale_error_vs_peclet.png` | checksum-bound Pe sweep | `cases/two_scale.../scripts/reproduce_paper_validation.py` |
| 14 | `png/fig10_two_scale_pe1_fields.png` | checksum-bound Pe=1 outputs | `cases/two_scale.../scripts/reproduce_paper_validation.py` |

Paths containing `tutorials/...` are abbreviated only in this table. The exact
paths, run commands, prerequisites, and evidence files are in
`../reproducibility_manifest.json`; detailed panel descriptions are preserved in
`png/manifest.md`.

Figures 10 and 11 require regenerated solver fields because raw production
fields are intentionally not stored in Git. Figures 13 and 14 use external run
archives whose identities and accepted checkpoints are checksum-bound by
`paper_validation_runs.json` and the repository-level `RUN_ARCHIVE_MANIFEST.md`.
The published PNGs are tracked for manuscript compilation in all cases.

The standard Python plotting dependencies are listed in `requirements.txt`.
Some 3D rendering wrappers additionally require ParaView's own Python runtime;
the wrapper scripts select that runtime explicitly.
