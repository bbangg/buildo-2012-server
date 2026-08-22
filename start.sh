#!/bin/zsh
# Bring up the local Buildo server and launch the patched client.
S=$HOME/buildo-server
G=$HOME/buildo-run
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
sleep 1

mkdir -p $G/cache
[ -f $G/cache/items.dat ] || cp $S/items.dat $G/cache/items.dat

cd $S
python3 $S/raw_httpd.py > $S/raw.log 2>&1 &
$S/gs                   > $S/gs.log  2>&1 &
sleep 1
echo "server_data responder : 127.0.0.1:$HTTP_PORT  (log: $S/raw.log)"
echo "game server (ENet)    : udp/17091       (log: $S/gs.log)"
echo
echo "In the game: click 'Play Online' (394,472) then 'Connect' (600,630)."
echo "Watch $S/gs.log to see the handshake."
cd $G && wine Buildo-local.exe
