#!/bin/zsh
# Ask the injected cap.dll for a memory dump.  probe.sh items|inv|world
C="$HOME/.wine-buildo/drive_c"
case "$1" in
  items) req=items.req; out=items.txt;;
  inv)   req=inv.req;   out=inv.txt;;
  world) req=world.req; out=world.txt;;
  bar)   req=bar.req;   out=bar.txt;;
  av)    req=av.req;    out=av.txt;;
  *) echo "usage: probe.sh items|inv|world|bar|av"; exit 2;;
esac
rm -f "$C/$out"; : > "$C/$req"
for i in $(seq 1 60); do [ -f "$C/$out" ] && break; sleep 0.1; done
sleep 0.3
[ -f "$C/$out" ] || { echo "no dump (cap.dll injected?)"; exit 1; }
cat "$C/$out"
