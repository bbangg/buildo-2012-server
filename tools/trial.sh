#!/bin/zsh
# One world-format experiment: launch, walk into START, report whether the
# client parsed the map.  Environment is passed straight through to gs.
cd $HOME/buildo-server
BUILDO_ITEMS=${BUILDO_ITEMS:-$HOME/buildo-server/tools/items_s2.dat} tools/run.sh START >/dev/null 2>&1
if grep -q "Loaded map" $HOME/buildo-run/log.txt; then
  echo "PARSED  $(grep -o 'Loaded map, [0-9]* bytes.*cells' $HOME/buildo-run/log.txt | tail -1)"
else
  echo "FAILED  (no 'Loaded map'; $(grep -c DISCONNECT $HOME/buildo-server/gs.log) disconnects)"
fi
