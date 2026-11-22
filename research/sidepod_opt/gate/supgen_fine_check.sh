#!/bin/bash
# fine-mesh compatibility of generated supports (not a drag number): fine mesh (car 4/5, supports 5/5),
# 30 iterations, then checkMesh and the captured supports patch. Waits for the coarse support runs.
cd /home/user/esp32-line-follower/research/sidepod_opt
until grep -q SUPGEN_CFD_DONE gate/supgen_cfd.log && ! pgrep -f "support_gen.py demo" >/dev/null && [ -f runs/support_gen/carved_tie_v2.done ]; do sleep 60; done
source /usr/lib/openfoam/openfoam2412/etc/bashrc 2>/dev/null
export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1
ulimit -v 6000000
# coarse run of the tie-carved supports first (same settings as supgen_cfd.sh), then its fine check
if [ ! -f gate_results_supgen/prodcheck_carved_tie.json ]; then
  echo "start carved_tie $(date -u +%T)"
  GATE_PLUS_SURFACES=supports PRODCHECK_RES=coarse PRODCHECK_RESULTS=$PWD/gate_results_supgen PRODCHECK_ITERS=2000 \
    PRODCHECK_KEEP=$PWD/gate/supgen_cases/carved_tie nice -n 5 /opt/py/bin/python -W ignore prodcheck.py \
    runs/support_gen/carved_tie/car carved_tie 2 cold > gate/prodcheck_supgen_carved_tie.log 2>&1
  ( cd gate/supgen_cases/carved_tie && surfaceMeshExtract -patches '(supports)' supports_cfd.obj > log.extract 2>&1 )
  echo "done carved_tie $(/opt/py/bin/python -c "import json;d=json.load(open('gate_results_supgen/prodcheck_carved_tie.json'));print(round(d['D20_half_N']*1e3,2),'mN cells',d.get('n_cells'),'conv',d['converged'])" 2>&1 | tail -1) $(date -u +%T)"
fi
OUT=$PWD/gate_results_supgen_fine; mkdir -p $OUT
K=$PWD/gate/supgen_cases/carved_tie_fine
# memory: the fine queue's solver holds ~5.6 GB (4 ranks x 1.4 GB VmHWM, 2026-11-22); a fine snappy of ~3.4 M
# cells needs a few GB more. ulimit is per process, so also wait for 8 GB available before starting.
until [ $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) -ge 8 ]; do sleep 120; done
echo "start carved_tie_fine $(date -u +%T) MemAvailable $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) GB"
GATE_PLUS_SURFACES=supports GATE_TIMEOUT=30000 PRODCHECK_RES=fine PRODCHECK_RESULTS=$OUT PRODCHECK_ITERS=30 PRODCHECK_KEEP=$K \
  nice -n 5 /opt/py/bin/python -W ignore prodcheck.py runs/support_gen/carved_tie/car carved_tie_fine 2 cold > gate/prodcheck_supgen_carved_tie_fine.log 2>&1
if grep -qiE "bad_alloc|MemoryError|Killed|Cannot allocate" gate/prodcheck_supgen_carved_tie_fine.log $K/logs/*.log 2>/dev/null; then
  echo "FINE CHECK: MEMORY FAILURE (not a compatibility verdict)"
elif [ -d $K/constant/polyMesh ]; then
  ( cd $K && checkMesh -latestTime > log.checkMesh_sup 2>&1; surfaceMeshExtract -patches '(supports)' supports_cfd.obj > log.extract 2>&1 )
  cells=$(grep -m1 "cells:" $K/log.checkMesh_sup | awk '{print $2}')
  verdict=$(grep -E "Mesh OK|Failed [0-9]+ mesh checks" $K/log.checkMesh_sup | tail -1)
  iters=$(tail -1 $K/postProcessing/forces/0/force.dat 2>/dev/null | awk '{print $1}')
  echo "FINE CHECK: cells $cells | checkMesh: ${verdict:-NO VERDICT} | supports patch faces: $(grep -cE '^f ' $K/supports_cfd_0.obj 2>/dev/null || echo 0) | last iteration: ${iters:-none}"
else
  echo "FINE CHECK: NO MESH KEPT (see gate/prodcheck_supgen_carved_tie_fine.log)"
fi
echo "SUPGEN_FINE_DONE $(date -u +%T)"
