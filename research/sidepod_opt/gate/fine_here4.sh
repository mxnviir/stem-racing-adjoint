#!/bin/bash
# after the fine groove~1 run: one medium pair for the wheel supports (ROUTES.md 2026-11-22 19:00), then the fine list
cd /home/user/esp32-line-follower/research/sidepod_opt
until [ -f "gate_results_fine/prodcheck_groove~1.json" ]; do sleep 60; done
pkill -f "bash gate/fine_here2.sh"; pkill -f "fine_campaign/campaign.sh forward"; sleep 2; pkill -f prodcheck.py; sleep 5
rm -f gate_results_fine/resources_adjoint8.json
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
source /usr/lib/openfoam/openfoam2412/etc/bashrc 2>/dev/null
export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 OMPI_MCA_rmaps_base_oversubscribe=1
for t in team_sup_cad "team_sup_cad~1"; do
  dx=0; [ "$t" = "team_sup_cad~1" ] && dx=0.37
  [ -f "gate_results_medium/prodcheck_$t.json" ] || GATE_DOMAIN_DX_MM=$dx PRODCHECK_RES=medium PRODCHECK_ITERS=2000 /opt/py/bin/python -W ignore prodcheck.py runs/fine_cars/team_sup_cad/car "$t" 4 cold > "gate/prodcheck_medium_$t.log" 2>&1
  [ -f "gate_results_medium/prodcheck_$t.json" ] && echo "done $t $(/opt/py/bin/python -c "import json;print(round(json.load(open('gate_results_medium/prodcheck_$t.json'))['D20_half_N']*1e3,2),'mN')") $(date -u +%T)" || echo "FAILED $t $(date -u +%T)"
done
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=2000
FORWARD_LIST="team~2 groove~2 nopod adjoint8 blend50" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
