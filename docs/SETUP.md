# Setup

From a bare macOS box to a running 2012 Growtopia world. Nothing here needs
root, nothing touches the system, and your copy of the original game is never
modified.

## 1. Get the original build

This repository contains **no game files**. Seth Robinson published the
prototype himself; get it from him, not from us:

    OldAssBuildoWinFrom2012.zip

Everything in [PROTOCOL.md](PROTOCOL.md) cites virtual addresses into that
exact binary. Check you have the same one before trusting an address:

    shasum -a 256 OldAssBuildoWinFrom2012.zip
    78a46dc3645c7173ef2ceecccdc9170019ad3a05b820c4aa1de00871eac1caef

    shasum -a 256 Buildo.exe
    fbec5a3c16af17c44c4eb54d43fc048df9f18fc9c3f0bc6fcef4ea8a7a933945

If your Buildo.exe hashes differently, say so in an issue before filing
anything address-shaped — a different build means every VA on these pages is
off.

## 2. Prerequisites

    brew install --cask wine-stable
    brew install enet mingw-w64 python@3.12
    xcode-select --install          # for c++

`mingw-w64` builds the three 32-bit helpers that load into the client; `enet`
is what the server speaks.

## 3. Lay out the tree

Three directories, all under `$HOME` — the scripts hardcode these paths:

    ~/buildo-run/            an isolated COPY of the game (its own log.txt,
                             so the original never gets written to)
    ~/buildo-server/         this repository
    ~/.wine-buildo/          a wine prefix of its own, so nothing else you
                             run under wine shares state with the game

    mkdir -p ~/buildo-run
    cp -R /path/to/OldAssBuildoWinFrom2012/* ~/buildo-run/
    WINEPREFIX=~/.wine-buildo wineboot -i

`ra.py` and `patch_client.py` read the **pristine** `Buildo.exe` from
`~/Downloads/OldAssBuildoWinFrom2012` by default. If yours is elsewhere, set
`BUILDO_SRC` to that directory.

## 4. Build

Nothing here is checked in as a binary artefact you cannot rebuild:

    # the server
    c++ -O2 -std=c++11 -o gs server.cpp \
        -I/opt/homebrew/include -L/opt/homebrew/lib -lenet

    # the injected helpers (32-bit, they load into the client)
    i686-w64-mingw32-gcc -O2 -shared -o tools/cap.dll tools/cap.c \
        -lopengl32 -lgdi32
    i686-w64-mingw32-gcc -O2 -o tools/inj.exe tools/inj.c
    i686-w64-mingw32-gcc -O2 -o tools/ui.exe  tools/ui.c -luser32

The Python tooling (`ra.py` for static analysis, `tools/itemsdat.py`) wants a
venv of its own — capstone and pefile:

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## 5. Patch the client

`patch_client.py` writes `Buildo-local.exe` beside the pristine `Buildo.exe`,
which it never modifies. Run it once:

    python3 patch_client.py

Each patch asserts its original bytes before writing, so a wrong build fails
loudly instead of producing a subtly broken exe.

The one that mattered: `App::GetServerInfo(string* host, int* port)` at
VA 0x402450 hardcodes BOTH the domain and the port —

    402450  mov ecx,[esp+4]
    402454  push 0x0A              ; strlen("rtsoft.com")
    402456  push 0x4C85AC          ; "rtsoft.com"      <-- the real domain
    40245B  call string_assign
    402460  mov eax,[esp+8]
    402464  mov dword [eax], 0x50  ; port 80           <-- the real port
    40246A  ret 8

    file 0x0C85AC  "rtsoft.com" -> "127.0.0.1"
    file 0x002455  push 0x0A    -> push 0x09
    file 0x002466  imm32 80     -> 8081
    plus the same for a secondary "hamumu.com" endpoint (0x0C9F80 / 0x01533B)
    and two unused port defaults (0x0305F7 / 0x0096F69).

"hamumu.com" is a decoy: it sits beside the "growtopia/server_data.php"
string and is the only host xref'd from that code, but the request actually
goes through the app's default domain, rtsoft.com.


## 6. Run

    ~/buildo-server/play.sh            # or: play.sh SOMEWORLD

Starts both servers, injects the frame grabber, launches the client and walks
it into a world. `tools/run.sh` is the same thing without regenerating
items.dat (use `BUILDO_ITEMS=` to pin a specific one for experiments).

To drive it by hand instead use `start.sh` and click:

    Play Online   (394, 472)
    Connect       (600, 630)
    world name    click (512, 330), type a name
    Start         (600, 630)

Logs: `gs.log` (game server), `raw.log` (server_data),
`~/buildo-run/log.txt` (the client's own log).


## Ports

`server_data` listens on **tcp/8081** (8080 was taken on the machine this was
built on). The port is baked into the exe, so changing it means editing
`patch_client.HTTP_PORT` and re-running `patch_client.py`. The launchers refuse
to start if that port is busy — `raw_httpd` used to just die on bind and the
client hung silently at "Connection succeeded".

The game server is ENet/UDP on **17091**.
