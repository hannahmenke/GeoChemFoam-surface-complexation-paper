# 3D Manuscript Case: HFO-Coated Kelvin Cell

## Source Asset

- image: `images/raw/Kelvin1-200x200x200.raw.tar.gz`, materialised from the
  immutable GeoChemFoam link in `external_assets.json` by
  `prepare_external_assets.sh` and not duplicated in Git
- metadata: `images/raw/Kelvin1-200x200x200.txt`

## Paper Role

- controlled 3D image-based reactive transport example
- critical-metal recovery analogue in an open-cell sorbent medium
- coupled flow, transport, and surface-complexation response in a 3D DBS case

## Geometry

- image size: `200 x 200 x 200`
- voxel size: `10 mum`
- labels:
  - `1 = pore`
  - `2 = microporous/reactive sorbent phase`

## Surface Model

- two-site Dzombak-Morel hydrous ferric oxide (HFO) surface complexation
- strong sites: `Surf_s = 2e-7 kmol/m2` in the OpenFOAM dictionary,
  equivalent to `2e-4 mol/m2`
- weak sites: `Surf_w = 6e-6 kmol/m2` in the OpenFOAM dictionary,
  equivalent to `6e-3 mol/m2`
- target species: Mn2+
- competing background species: Mg2+
- initial and inlet Mg2+: `1e-3 mol/L`
- inlet Mn2+: `1e-5 mol/L`

Mn2+ has stronger HFO affinity than Mg2+ in the Dzombak-Morel reaction set, so
the injected Mn-bearing front is preferentially captured from Mg-rich water.

## Surface Area

- `aSurf` reconstructed from Gaussian-smoothed phase occupancy with
  `sigma = 0.75` voxel
- intrinsic micropore contribution inside label `2`
- intrinsic micropore density: `1e5 1/m`

## Reproducibility

The paper-local executable case is
`tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`.
Run the full case from that directory:

```bash
export GCFOAM_RUNTIME_ROOT=/absolute/path/to/reviewed-runtime
export KELVIN_EXPECTED_GCFOAM_COMMIT=/reviewed/GeoChemFoam/commit
export KELVIN_EXPECTED_GCFOAM_TREE=/reviewed/GeoChemFoam/tree
export KELVIN_EXPECTED_PHREEQCRM_GITLINK=/reviewed/superproject/gitlink
export KELVIN_EXPECTED_PHREEQCRM_COMMIT=/reviewed/PHREEQCRM/commit
export KELVIN_EXPECTED_PHREEQCRM_TREE=/reviewed/PHREEQCRM/tree
export TOTAL_TIME=/reviewed/stage/endpoint
export WRITE_TIMESTEP=/reviewed/stage/interval
export RUN_TIMESTEP=/accepted/timestep
./runAll.sh
```

The script creates the mesh, runs flow, runs reactive transport, and performs
the configured post-processing. The transport values are intentionally
required at launch so that convergence-pilot settings cannot become implicit
production settings.

## Figures

- `figures/png/fig03_3d_kelvin.png`
- `figures/png/fig07_kelvin_temporal.png`

Regenerate both figures after a completed run with:

```bash
KELVIN_REPO_ROOT="$(git rev-parse --show-toplevel)"
"$KELVIN_REPO_ROOT/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_kelvin_mnmg_figures.sh"
```
