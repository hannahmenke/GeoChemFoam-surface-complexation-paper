# 3DEstailladesMicroporeAsSolidSurfaceComplexation

Presentation comparison case derived from `3DEstailladesSurfaceComplexation`.

Purpose:
- keep the same Estaillades image and chemistry setup
- remap the micropore label to solid before `eps` and `aSurf` are generated
- retain surface complexation only on pore-solid walls

This makes the case a binary pores-plus-solids comparison against the original
DBS pores-plus-micropores-plus-solids setup.

Key differences from the original Estaillades case:
- `createMesh.sh` remaps image label `2 -> 3` locally in the copied raw image
- `initCaseFlow.sh` and `initCaseTransport.sh` use two phases only
- `initCaseReactiveTransport.sh` generates `aSurf` from wall area only, with no
  intrinsic micropore surface-area contribution
