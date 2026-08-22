#!/bin/zsh
# Grab the OpenGL framebuffer from the running client and convert it to PNG.
# Requires cap.dll to be injected (play.sh does it).  Usage: shot.sh [out.png]
export PATH="/opt/homebrew/bin:$PATH"
export WINEPREFIX="$HOME/.wine-buildo"
C="$WINEPREFIX/drive_c"
OUT=${1:-$HOME/buildo-server/shot.png}
rm -f "$C/shot.bmp" "$C/shot.req"
: > "$C/shot.req"
for i in $(seq 1 60); do
  [ -f "$C/shot.bmp" ] && [ ! -f "$C/shot.req" ] && sleep 0.2 && break
  sleep 0.1
done
if [ ! -f "$C/shot.bmp" ]; then echo "no frame captured (cap.dll injected?)"; exit 1; fi
sips -s format png "$C/shot.bmp" --out "$OUT" >/dev/null 2>&1 || { echo "sips failed"; exit 1; }
echo "$OUT"
