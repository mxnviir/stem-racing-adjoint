#!/bin/bash
# fine queue relaunch after the container restart of 2026-11-23 ~03:15 UTC killed team~2 at iteration 895 (no checkpoint written)
# 2026-11-23 06:10: owner set the remaining fine runs to 1000 iterations (was 2000); restarted team~2 during meshing
cd /home/user/esp32-line-follower/research/sidepod_opt
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=1000
FORWARD_LIST="team~2 groove~2 nopod adjoint8 blend50" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
