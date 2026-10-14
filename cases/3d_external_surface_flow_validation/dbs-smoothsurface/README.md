# 3DEstailladesMicroporeAsSolidSurfaceComplexation

Paper-local runnable copy of the binary Estaillades comparison case, derived from `3DEstailladesSurfaceComplexation`.

Purpose:
- keep the same Estaillades image and chemistry setup
- remap the micropore label to solid before `eps` and `aSurf` are generated
- retain surface complexation only on pore-solid walls

This makes the case a binary pores-plus-solids comparison against the original
DBS pores-plus-micropores-plus-solids setup.

Paper-local status:
- this copy exists so the paper workflow does not depend on edits or run artefacts under `tutorials/`
- it is intended to be run from:
  - `cases/3d_estaillades_micropore_as_solid`
- generated mesh, `triSurface`, processor directories, and logs should remain untracked here

Key differences from the original Estaillades case:
- `createMesh.sh` remaps image label `2 -> 3` locally in the copied raw image
- `initCaseFlow.sh` and `initCaseTransport.sh` use two phases only
- `initCaseReactiveTransport.sh` generates `aSurf` from wall area only, with no
  intrinsic micropore surface-area contribution

How to run:
```bash
cd cases/3d_estaillades_micropore_as_solid
./runAll.sh
```
