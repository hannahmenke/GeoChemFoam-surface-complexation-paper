# Manuscript PNG Figures

This directory is the staging location for manuscript PNG outputs.

Geometry palette rule:

- pore: white / clear
- micropore or intermediate porous phase: blue
- solid: red

Figure targets:

- `fig01_1d_retardation.png`
- `fig02_2d_fractures.png`
- `fig03_3d_kelvin.png`
- `fig04_3d_estaillades.png`
- `fig05_solver_workflow.png`
- `fig06_1d_breakthrough.png`
- `fig07_kelvin_temporal.png`
- `fig08_estaillades_temporal.png`
- `fig09_sphere_surface_area_validation.png`
- `fig10_hm12_surface_area_validation.png`
- `fig11_3d_external_surface_area_validation.png`
- `fig12_two_scale_lithium_nested_geometries.png`
- `fig10_two_scale_pe1_fields.png` (manuscript Figure 8)
- `fig09_two_scale_error_vs_peclet.png` (manuscript Figure 9)

Current staged figures:

- `fig01_1d_retardation.png`
  - two-panel 1D analytical validation figure
  - left: normalized aqueous profile vs cell-averaged analytical reference
  - right: normalized surface loading vs cell-averaged linear-limit reference
- `fig02_2d_fractures.png`
  - three-panel 2D results figure for Pb²⁺ / Dzombak–Morel HFO
  - left: fracture geometry
  - middle: log-scale Pb²⁺ / C_in at `t = 20000` (4 decades, fracture vs. micropore contrast)
  - right: log-scale Hfo_sOPb⁺/Hfo_s,total strong-site occupancy at `t = 20000`
  - uses the higher-load Pb case (`C_in = 10^-3 mol m^-3`), showing strong but incomplete retardation by HFO
- `fig03_3d_kelvin.png`
  - five-panel Kelvin competition figure, t = 120 s
  - top: segmented geometry
  - lower 2x2: dissolved Mn²⁺, dissolved Mg²⁺, ΔHFO-Mn, and displaced HFO-Mg
- `fig04_3d_estaillades.png`
  - native-500³, 64-rank 3D volume renders at t = 40 s
  - grayscale segmented exterior, dissolved Sr²⁺ and Ca²⁺ over pore and micropore water,
    and max-normalised incremental adsorbed Sr (Surf_aSr⁺) in the reactive phase
- `fig07_kelvin_temporal.png`
  - two-panel temporal evolution for Kelvin Mn²⁺/Mg²⁺ competitive sorption
  - left: domain-mean Mg²⁺ excess above background and Mn²⁺/C_in vs time
  - right: normalised incremental HFO-Mn and displaced HFO-Mg domain-mean vs time
- `fig08_estaillades_temporal.png`
  - two-panel temporal evolution for Estaillades Sr²⁺/Ca²⁺ chromatographic exchange
  - left: pore-volume-weighted Ca²⁺ / C_init and Sr²⁺ / C_in vs time (7 time points, t = 0--120 s)
  - right: incremental surface-area-weighted Surf_aCa⁺ and Surf_aSr⁺ vs time,
    normalised by the largest absolute change over the plotted sequence
- `fig09_sphere_surface_area_validation.png`
  - controlled sphere and circular-post tests of integrated interface area
- `fig10_hm12_surface_area_validation.png`
  - resolved-wall and DBS micromodel comparison of aqueous concentration, reactive area, and sorbed inventory
- `fig11_3d_external_surface_area_validation.png`
  - resolved-wall and DBS external-area comparison for the 3D Estaillades crop
- `fig12_two_scale_lithium_nested_geometries.png`
  - aligned resolved, upscaled, and matrix-REV geometries for the lithium benchmark
- `fig10_two_scale_pe1_fields.png` (manuscript Figure 8)
  - native 5 µm Pe = 1 aqueous and sorbed Li fields at `x/L = 0.625`
  - resolved grains are masked and no display averaging is applied

The LaTeX draft references the current PNG outputs and uses a framed placeholder
for Figure 9 until the standardized sweep data are supplied.

Repeatable figure commands:

- 1D validation figures:
  - `../scripts/render_1d_validation_figures.sh`
- 2D fracture figure:
  - `../scripts/render_2d_fractures_figure.sh`
- Kelvin Mn/Mg figures:
  - `../scripts/render_kelvin_mnmg_figures.sh`
- Estaillades figures:
  - `../scripts/render_estaillades_figures.sh`
- surface-area validation figures:
  - `../scripts/render_surface_area_validation_figures.sh`
- two-scale lithium sorption validation:
  - `../scripts/render_two_scale_lithium_sorption_validation.sh`
  - current Pe=1 field figure: `../../cases/two_scale_micromodel_sorption_validation/scripts/reproduce_paper_validation.py`
  - verified Pe-sweep comparison: `../../cases/two_scale_micromodel_sorption_validation/scripts/reproduce_paper_validation.py`
- all core manuscript figures with completed outputs available:
  - `../scripts/render_core_manuscript_figures.sh`

The authoritative Figure 1--14 mapping, including historical filename
numbering that differs from manuscript order, is `../../reproducibility_manifest.json`.
The compact human-readable table is `../README.md`.

## Accepted non-Kelvin provenance check

The authoritative machine-readable manifest for accepted Figures 2, 3, 10,
13, and 14 is `../accepted_nonkelvin_provenance.json`. It binds each retained PNG to
its material data, renderer sources, and case-specific evidence without
rewriting the historical provenance schemas. From the repository root, run:

```sh
validate_accepted_nonkelvin_artifacts.sh
```

The command runs the fail-closed verifier and its tampering tests. It is also
run before the normal manuscript build. The manifest is hand maintained; the
verifier never discovers files or updates hashes.
