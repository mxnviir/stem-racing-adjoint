#!/bin/bash
# fine mesh: the groove flipped sign vs medium (ROUTES.md 2026-11-22 09:40) -> clean repeats of team and groove first
cd /home/user/esp32-line-follower/research/sidepod_opt
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=2000
FORWARD_LIST="team~1 groove~1 adjoint8 nopod blend50" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
