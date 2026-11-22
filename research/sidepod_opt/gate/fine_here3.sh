#!/bin/bash
# fine mesh: the team pod's two fine meshes differ by 3.8 mN (ROUTES.md 2026-11-22 14:45) -> more repeats of
# team and groove before any single design. Takes over after groove~1 finishes.
cd /home/user/esp32-line-follower/research/sidepod_opt
until [ -f "gate_results_fine/prodcheck_groove~1.json" ]; do sleep 60; done
pkill -f "bash gate/fine_here2.sh"; pkill -f "fine_campaign/campaign.sh forward"; sleep 2; pkill -f prodcheck.py; sleep 5
rm -f gate_results_fine/resources_adjoint8.json
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=2000
FORWARD_LIST="team~2 groove~2 nopod adjoint8 blend50" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
