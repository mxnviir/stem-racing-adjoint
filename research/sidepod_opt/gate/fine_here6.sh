#!/bin/bash
# fine queue relaunch after the container restart of 2026-11-23 ~03:15 UTC killed team~2 at iteration 895 (no checkpoint written)
cd /home/user/esp32-line-follower/research/sidepod_opt
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=2000
FORWARD_LIST="team~2 groove~2 nopod adjoint8 blend50" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
