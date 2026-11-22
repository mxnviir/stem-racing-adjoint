#!/bin/bash
# fine queue after the out-of-memory kill of groove~1 (ROUTES.md 2026-11-22 19:40): repeats first, then the rest
cd /home/user/esp32-line-follower/research/sidepod_opt
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=2000
FORWARD_LIST="groove~1 team~2 groove~2 nopod adjoint8 blend50" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
