#!/bin/zsh
# Start the local Buildo server, launch the client, and walk it into a world.
# Usage: play.sh [worldname]
S=$HOME/buildo-server
G=$HOME/buildo-run
WORLD=${1:-START}
export PATH="/opt/homebrew/bin:$PATH"
export WINEPREFIX="$HOME/.wine-buildo"
export WINEDEBUG=-all

# Fail loudly if our HTTP port is taken by something else (a stale dev server
# here once made the client hang with no error at all). Runs after we kill our own
# responder, so a leftover of ours is not mistaken for a foreign process.

pkill -f "buildo-server/raw_httpd.py" 2>/dev/null
sleep 1
HTTP_PORT=${BUILDO_HTTP_PORT:-8081}
OWNER=$(lsof -nP -iTCP:$HTTP_PORT -sTCP:LISTEN -t 2>/dev/null | grep -v "^$$" | head -1)
if [ -n "$OWNER" ]; then
  echo "ERROR: tcp/$HTTP_PORT is already in use by pid $OWNER:"
  ps -o pid,command -p $OWNER | tail -1
  echo "Free it, or set BUILDO_HTTP_PORT and re-run patch_client.py with the same value."
  exit 1
fi
export BUILDO_HTTP_PORT=$HTTP_PORT
P=$(lsof -nP -iUDP:17091 -t 2>/dev/null | head -1); [ -n "$P" ] && kill $P
wineserver -k 2>/dev/null
sleep 2

mkdir -p $G/cache
python3 $S/make_items.py > /dev/null
cp -f $S/items.dat $G/cache/items.dat

cd $S
python3 $S/raw_httpd.py > $S/raw.log 2>&1 &
BUILDO_WORLDS=$'START\nSECOND\nTHIRD' $S/gs > $S/gs.log 2>&1 &
sleep 1
echo "server_data  : 127.0.0.1:$HTTP_PORT   ($S/raw.log)"
echo "game server  : udp/17091        ($S/gs.log)"
echo "world        : $WORLD"
echo

: > $G/log.txt
cd $G && wine Buildo-local.exe > /dev/null 2>&1 &

# wait for the renderer to come up
for i in $(seq 1 40); do
  grep -q "TextManager initialized" $G/log.txt 2>/dev/null && break
  sleep 1
done
sleep 3

# Inject the framebuffer grabber: the game renders with OpenGL, so the only
# place its pixels can be read is inside the process with the GL context
# current (GDI BitBlt returns black, macOS screencapture is not permitted).
CAPDLL="Z:$(printf '%s' "$S/tools/cap.dll" | sed 's|/|\\|g')"
WINEDEBUG=-all wine $S/tools/inj.exe Buildo-local "$CAPDLL" 2>&1 | tail -1

poke() { WINEDEBUG=-all wine $S/poke.exe "$@" > /dev/null 2>&1 }
echo "-> Play Online";  poke click 394 472; sleep 3
echo "-> Connect";      poke click 600 630; sleep 5
echo "-> world name";   poke click 512 330; sleep 1; poke rtext "$WORLD"; sleep 1
echo "-> Start";        poke click 600 630; sleep 6
# The UI clicks leave the game believing the mouse is still held on
# the on-screen controls, which walks the avatar around on its own.
echo "-> release input"; poke release; sleep 1

echo
# NB: macOS pgrep has no -c flag -- "pgrep -fc" always fails and prints 0,
# which is what made a perfectly live client look like it had crashed.
ALIVE=$(pgrep -f Buildo-local.exe | wc -l | tr -d ' ')
if grep -q "Loaded map" $G/log.txt; then
  grep -E "Loaded map|Took .* map load" $G/log.txt | tail -2
  if [ "$ALIVE" = "0" ]; then
    echo
    echo "The map parsed but the client is gone. Re-run under ./dbg.sh to get"
    echo "the Wine exception log ($S/seh.log) and the wine exit code."
  else
    echo
    echo "IN WORLD - client alive (pid $(pgrep -f Buildo-local.exe | head -1))."
    echo "Window 'Growtopia' is up; input goes through: wine poke.exe rkey <vk>"
  fi
else
  echo "did not reach the world - see $G/log.txt and $S/gs.log"
fi
