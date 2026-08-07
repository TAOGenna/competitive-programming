"""`python3 -m vrating [handle ...]` — start the server and open the page.

The whole app in one command. Given handles it also warms their contests in the background,
so the first replay is quick; without them the cache fills itself as you use it.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


def _free_port(preferred: int) -> int:
    """Use the preferred port, or the next thing free — a stale server should not block us."""
    for port in range(preferred, preferred + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"no free port in {preferred}..{preferred + 19}")


def _warm(handles):
    from .sources import prewarm
    try:
        done, _ = prewarm.prewarm_for(handles, log=lambda m: None)
        print(f"  cache warm: {done} contests ready", flush=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"  cache warming stopped ({type(exc).__name__}); "
              f"the app still works, just slower on first use", flush=True)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    handles = [a for a in argv if not a.startswith("-")]

    try:
        import numpy                                           # noqa: F401
    except ImportError:
        print("vrating needs numpy:\n\n    pip install -r requirements.txt\n", file=sys.stderr)
        return 1

    from .web import server

    port = _free_port(int(os.environ.get("VRATING_PORT", "8770")))
    url = f"http://127.0.0.1:{port}/"
    if handles:
        url += "#" + handles[0]

    say = lambda m: print(m, flush=True)   # unbuffered: this banner is the only feedback
    say(f"vrating → {url}")
    if handles:
        say(f"  warming {', '.join(handles)} in the background…")
        threading.Thread(target=_warm, args=(handles,), daemon=True).start()
    else:
        say("  tip: pass your handle to warm its contests up front")
    say("  ctrl-c to stop")

    threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                     daemon=True).start()
    try:
        server.main(port=port, host="127.0.0.1", banner=False)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
