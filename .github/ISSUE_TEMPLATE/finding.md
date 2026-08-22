---
name: Finding
about: Something you worked out about the 2012 client
title: ''
labels: finding
---

**Claim**
One sentence. What does the client do?

**Static evidence**
Virtual addresses into the unpatched `Buildo.exe`
(sha256 `fbec5a3c…933945`) and what is there — the compare, the jump table
entry, the string, the field offset.

**Dynamic confirmation**
What you saw on a running client: a `shot.sh` PNG, a `probe.sh` dump, a line
from `log.txt`. Before and after if it is a fix.

**What this is NOT**
The boundary of the claim. Which part is pinned by the binary and which part
is your attribution?

<!-- Only part 1? Say so — a hypothesis is still welcome, it just does not go
     into the docs as fact. See CONTRIBUTING.md. -->
