#!/usr/bin/env python3
"""Drive one Buildo run: launch, click Online, report what the client did."""
import os, subprocess, time, pathlib, sys

GAME = pathlib.Path.home()/"buildo-run"
S    = pathlib.Path.home()/"buildo-server"
ENV  = {**os.environ,
        "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH",""),
        "WINEPREFIX": str(pathlib.Path.home()/".wine-buildo"),
        "WINEDEBUG": "-all"}

def sh(*a, **kw):
    return subprocess.run(a, env=ENV, cwd=str(GAME), capture_output=True, text=True, **kw)

def kill_all():
    sh("wineserver", "-k"); time.sleep(2.5)

def launch():
    (GAME/"log.txt").write_text("")
    subprocess.Popen(["wine", "Buildo-local.exe"], env=ENV, cwd=str(GAME),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            if "TextManager initialized" in (GAME/"log.txt").read_text(errors="replace"):
                return True
        except FileNotFoundError: pass
        time.sleep(1)
    return False

def window_ok():
    out = sh("wine", str(S/"poke.exe"), "list").stdout
    wins = [l for l in out.splitlines() if "class='AppClass'" in l and "vis=1" in l]
    return wins

def click(x, y):
    return sh("wine", str(S/"poke.exe"), "click", str(x), str(y)).stdout.strip()

def log():           return (GAME/"log.txt").read_text(errors="replace")
def httplog():       return (S/"http.log").read_text(errors="replace")

def run(label, mode, body, cx=512, cy=460, wait=9):
    (S/"mode.txt").write_text(mode)
    (S/"response.txt").write_bytes(body)
    kill_all()
    if not launch():
        print(f"{label:22} mode={mode:9} -> LAUNCH FAILED"); return
    wins = window_ok()
    if len(wins) != 1:
        print(f"{label:22} mode={mode:9} -> expected 1 window, got {len(wins)}"); return
    time.sleep(1.5)
    http_before = httplog().count("[http] POST")
    log_before  = log().count("Clicked")
    click(cx, cy)
    time.sleep(wait)
    lg = log()
    clicked = lg.count("Clicked") > log_before
    posts   = httplog().count("[http] POST") - http_before
    marks = [m for m in ("Game menu killed", "Downloaded", "ERROR", "Connection succeeded",
                         "Logging on") if m in lg]
    print(f"{label:22} mode={mode:9} click={clicked} posts={posts} -> {marks or '<nothing>'}")
    for line in lg.splitlines():
        if any(k in line for k in ("Downloaded","ERROR","menu killed","Connection")):
            print("      |", line.strip())

if __name__ == "__main__":
    body = b"server|127.0.0.1\nport|17091\ntype|1\nRTENDMARKERBS1001"
    run("baseline", "h10", body)
