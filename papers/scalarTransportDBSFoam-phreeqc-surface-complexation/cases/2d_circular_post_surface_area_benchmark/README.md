# 2D circular-post surface-area benchmark

This controlled benchmark supplies the circular-post series in manuscript
Figure 9. The tracked `results/area_metrics.csv` contains the accepted
`snappyHexMesh` measurements. `runAll.sh` regenerates temporary meshes for post
radii of 8, 16, 32, and 64 cells and rewrites that CSV; it requires an activated
OpenFOAM environment.

The benchmark generator is
`../../figures/scripts/run_2d_circular_post_snappy_benchmark.py`. The publication
figure combines these measurements with the 3D sphere results through
`../../figures/scripts/render_surface_area_validation_figures.sh`.
