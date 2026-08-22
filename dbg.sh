#!/bin/zsh
# Same as play.sh but runs the client under WINEDEBUG so the throw is visible.
# Usage: dbg.sh [worldname] [wine-debug-channels]
S=$HOME/buildo-server
G=$HOME/buildo-run
WORLD=${1:-START}
CHAN=${2:-+seh}
export PATH="/opt/homebrew/bin:$PATH"
export WINEPREFIX="$HOME/.wine-buildo"

pkill -f "buildo-server/raw_httpd.py" 2>/dev/null
sleep 1
HTTP_PORT=${BUILDO_HTTP_PORT:-8081}
OWNER=$(lsof -nP -iTCP:$HTTP_PORT -sTCP:LISTEN -t 2>/dev/null | head -1)
if [ -n "$OWNER" ]; then echo "ERROR: tcp/$HTTP_PORT busy (pid $OWNER)"; exit 1; fi
export BUILDO_HTTP_PORT=$HTTP_PORT
P=$(lsof -nP -iUDP:17091 -t 2>/dev/null | head -1); [ -n "$P" ] && kill $P
WINEDEBUG=-all wineserver -k 2>/dev/null
sleep 2

mkdir -p $G/cache
python3 $S/make_items.py > /dev/null
cp -f $S/items.dat $G/cache/items.dat

cd $S
WINEDEBUG=-all python3 $S/raw_httpd.py > $S/raw.log 2>&1 &
BUILDO_WORLDS=$'START\nSECOND\nTHIRD' $S/gs > $S/gs.log 2>&1 &
sleep 1

: > $G/log.txt
: > $S/seh.log
echo "channels: $CHAN   -> $S/seh.log"
: > $S/exit.txt
( cd $G && WINEDEBUG=$CHAN wine Buildo-local.exe > /dev/null 2> $S/seh.log
  echo "EXIT=$? (128+n means killed by signal n)" > $S/exit.txt ) &

for i in $(seq 1 60); do
  grep -q "TextManager initialized" $G/log.txt 2>/dev/null && break
  sleep 1
done
sleep 3

poke() { WINEDEBUG=-all wine $S/poke.exe "$@" > /dev/null 2>&1 }
echo "-> Play Online";  poke click 394 472; sleep 3
echo "-> Connect";      poke click 600 630; sleep 5
echo "-> world name";   poke click 512 330; sleep 1; poke rtext "$WORLD"; sleep 1
echo "-> Start";        poke click 600 630; sleep 8
# The UI clicks leave the game believing the mouse is still held on
# the on-screen controls, which walks the avatar around on its own.
echo "-> release input"; poke release; sleep 1

echo "alive: $(pgrep -f Buildo-local.exe | wc -l | tr -d ' ')   seh.log: $(wc -l < $S/seh.log) lines"
echo "wine $(cat $S/exit.txt)"
