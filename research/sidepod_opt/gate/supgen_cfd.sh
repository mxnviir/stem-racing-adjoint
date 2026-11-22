#!/bin/bash
# generated wheel supports: coarse plumbing CFD (D6: plumbing only), supports surface refined, cases kept
cd /home/user/esp32-line-follower/research/sidepod_opt
until [ -f runs/support_gen/carved/car/supports.stl ] && ! pgrep -f "support_gen.py demo" >/dev/null; do sleep 30; done
source /usr/lib/openfoam/openfoam2412/etc/bashrc 2>/dev/null
export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1
OUT=$PWD/gate_results_supgen; mkdir -p $OUT gate/supgen_cases
for job in "runs/fine_cars/team_sup_cad/car team_cad" "runs/support_gen/random_b/car random_b" "runs/support_gen/carved/car carved" "runs/support_gen/envelope/car envelope"; do
  set -- $job
  [ -f $OUT/prodcheck_$2.json ] && continue
  echo "start $2 $(date -u +%T)"
  GATE_PLUS_SURFACES=supports PRODCHECK_RES=coarse PRODCHECK_RESULTS=$OUT PRODCHECK_ITERS=2000 PRODCHECK_KEEP=$PWD/gate/supgen_cases/$2 \
    nice -n 5 /opt/py/bin/python -W ignore prodcheck.py $1 $2 2 cold > gate/prodcheck_supgen_$2.log 2>&1
  if [ -f $OUT/prodcheck_$2.json ]; then
    ( cd gate/supgen_cases/$2 && surfaceMeshExtract -patches '(supports)' supports_cfd.obj > log.extract 2>&1 )
    echo "done $2 $(/opt/py/bin/python -c "import json;d=json.load(open('$OUT/prodcheck_$2.json'));print(round(d['D20_half_N']*1e3,2),'mN cells',d.get('n_cells'),'conv',d['converged'])") $(date -u +%T)"
  else echo "FAILED $2 $(date -u +%T)"; fi
done
echo SUPGEN_CFD_DONE
