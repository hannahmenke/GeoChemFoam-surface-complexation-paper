# 3D Sphere Surface-Area Benchmark

This benchmark prepares a perfectly symmetric voxelized sphere together with the
two reference surface areas needed for the surface-area comparison:

1. the analytic smooth-sphere area `4*pi*R^2`
2. the exact voxel-face area of the rasterized binary sphere

The benchmark is intentionally split into two stages.

Stage 1, implemented here:
- generate a symmetric binary sphere for a resolution sweep
- generate an analytic sphere STL for the snappy path
- compute and save the two reference areas

Stage 2, to be executed on top of these generated assets:
- mesh the analytic sphere with `snappyHexMesh`
- reconstruct the binary-image interface with the explicit smoothed
  marching-cubes method used by the paper cases
- compare both geometric surface areas against the analytic and voxel-face
  references

How to run the geometry/reference sweep:

```bash
cd papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark
./runAll.sh
```

How to run the mesh-only area comparison after the assets exist:

```bash
cd papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark
./runMeshOnlyBenchmark.sh 8 16 32 64
```

What `runAll.sh` writes:
- `generated/sphere_r08/`
- `generated/sphere_r16/`
- `generated/sphere_r32/`
- `generated/sphere_r64/`

Each generated directory contains:
- `<name>.raw`
- `<name>.raw.tar.gz`
- `<name>_analytic.stl`
- `<name>.json`

The JSON contains:
- the analytic smooth-sphere area
- the exact voxel-face area
- symmetry checks
- grid and radius metadata

The geometry generator is:
- `scripts/generate_symmetric_sphere_geometry.py`

The area-measurement utility is:
- `scripts/measureSphereSurfaceArea.py`

Notes:
- the generator uses odd `N` in each direction so the sphere centre lies on the
  central cell centre
- the rasterized sphere is therefore exactly mirror-symmetric in `x`, `y`, and
  `z`
- this benchmark is meant to separate voxelization error from surface-method
  error, which is why both analytic and voxel-face reference areas are saved
- the benchmark is mesh-only; it does not require flow, transport, or chemistry
  solves
- the higher-resolution meshes are large, so individual levels may be supplied
  to `runMeshOnlyBenchmark.sh`
