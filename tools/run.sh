#!/bin/zsh
# Launch the client into a world, inject cap.dll, and leave it running.
# Same walkthrough as play.sh but it never regenerates items.dat -- pass one
# in with BUILDO_ITEMS so experiments are reproducible while other work is
# touching make_items.py.
#   tools/run.sh [WORLD]
S=$HOME/buildo-server
G=$HOME/buildo-run
T=$S/tools
WORLD=${1:-START}
export PATH="/opt/homebrew/bin:$PATH"
export WINEPREFIX="$HOME/.wine-buildo"
export WINEDEBUG=-all
export BUILDO_ITEMS=${BUILDO_ITEMS:-$S/items.dat}

pkill -f "buildo-server/raw_httpd.py" 2>/dev/null
pkill -f "buildo-server/gs" 2>/dev/null
sleep 1
HTTP_PORT=${BUILDO_HTTP_PORT:-8081}
OWNER=$(lsof -nP -iTCP:$HTTP_PORT -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ -n "$OWNER" ]; then echo "ERROR: tcp/$HTTP_PORT busy (pid $OWNER)"; exit 1; fi
export BUILDO_HTTP_PORT=$HTTP_PORT
P=$(lsof -nP -iUDP:17091 -t 2>/dev/null | head -1); [ -n "$P" ] && kill $P
wineserver -k 2>/dev/null
sleep 2

mkdir -p $G/cache
cp -f "$BUILDO_ITEMS" $G/cache/items.dat

cd $S
python3 $S/raw_httpd.py > $S/raw.log 2>&1 &
BUILDO_WORLDS=${BUILDO_WORLDS:-$'START\nSECOND\nTHIRD'} $S/gs > $S/gs.log 2>&1 &
sleep 1
: > $G/log.txt
cd $G && wine Buildo-local.exe > /dev/null 2>&1 &

for i in $(seq 1 40); do
  grep -q "TextManager initialized" $G/log.txt 2>/dev/null && break
  sleep 1
done
sleep 3
CAPDLL="Z:$(printf '%s' "$T/cap.dll" | sed 's|/|\\|g')"
WINEDEBUG=-all wine $T/inj.exe Buildo-local "$CAPDLL" 2>&1 | tail -1

poke() { WINEDEBUG=-all wine $S/poke.exe "$@" > /dev/null 2>&1 }
poke click 394 472; sleep 3
poke click 600 630; sleep 5
poke click 512 330; sleep 1; poke rtext "$WORLD"; sleep 1
poke click 600 630; sleep 6
poke release; sleep 1
poke release; sleep 1

ALIVE=$(pgrep -f Buildo-local.exe | wc -l | tr -d ' ')
grep -E "Loaded map|Can't|Error" $G/log.txt | tail -5
echo "alive=$ALIVE  items=$BUILDO_ITEMS  world=$WORLD"
