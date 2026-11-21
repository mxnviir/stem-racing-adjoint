#!/bin/bash
# gate 1 of the selected route on this machine: fine mesh, stage 0 (team), then the key designs (ROUTES.md 2026-11-21 21:45)
cd /home/user/esp32-line-follower/research/sidepod_opt
swapon --show | grep -q swapfile || swapon /swapfile 2>/dev/null
export PY=/opt/py/bin/python RES=fine NP=4 ITERS=2000
bash fine_campaign/campaign.sh stage0
FORWARD_LIST="groove nopod blend50 adjoint8 team~1 groove~1" bash fine_campaign/campaign.sh forward
echo FINE_HERE_DONE
