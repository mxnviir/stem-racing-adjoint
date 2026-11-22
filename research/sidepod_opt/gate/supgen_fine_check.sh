#!/bin/bash
# fine-mesh compatibility of generated supports (not a drag number): fine mesh (car 4/5, supports 5/5),
# 30 iterations, then checkMesh and the captured supports patch. Waits for the coarse support runs.
cd /home/user/esp32-line-follower/research/sidepod_opt
until grep -q SUPGEN_CFD_DONE gate/supgen_cfd.log; do sleep 60; done
source /usr/lib/openfoam/openfoam2412/etc/bashrc 2>/dev/null
export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1
ulimit -v 6000000
OUT=$PWD/gate_results_supgen_fine; mkdir -p $OUT
K=$PWD/gate/supgen_cases/carved_fine
echo "start carved_fine $(date -u +%T)"
GATE_PLUS_SURFACES=supports GATE_TIMEOUT=30000 PRODCHECK_RES=fine PRODCHECK_RESULTS=$OUT PRODCHECK_ITERS=30 PRODCHECK_KEEP=$K \
  nice -n 5 /opt/py/bin/python -W ignore prodcheck.py runs/support_gen/carved/car carved_fine 2 cold > gate/prodcheck_supgen_carved_fine.log 2>&1
if [ -d $K ]; then
  ( cd $K && checkMesh -latestTime > log.checkMesh_sup 2>&1; surfaceMeshExtract -patches '(supports)' supports_cfd.obj > log.extract 2>&1 )
  grep -E "cells:|Failed|Mesh OK|supports " $K/log.checkMesh_sup | head
fi
echo "SUPGEN_FINE_DONE $(date -u +%T)"
