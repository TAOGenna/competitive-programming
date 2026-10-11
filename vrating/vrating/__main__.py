"""`python3 -m vrating [handle ...]` — start the server and open the page.

The whole app in one command. Given handles it also warms their contests in the background,
so the first replay is quick; without them the cache fills itself as you use it.

Handles come from the command line, or from VRATING_HANDLES in `.env` when none are given —
so the accounts you always want are already loaded when the page opens.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.parse
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
    from .career import engine
    from .sources import prewarm
    try:
        # Resolve renames first: an old handle and its current one are one account, and
        # warming both would fetch the same contests twice.
        done, _ = prewarm.prewarm_for(engine.canonical_handles(handles), log=lambda m: None)
        print(f"  cache warm: {done} contests ready", flush=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"  cache warming stopped ({type(exc).__name__}); "
              f"the app still works, just slower on first use", flush=True)


def main(argv=None) -> int:
    from . import config

    argv = sys.argv[1:] if argv is None else argv
    handles = [a for a in argv if not a.startswith("-")] or config.handles()
    from_env = not [a for a in argv if not a.startswith("-")] and bool(handles)

    try:
        import numpy                                           # noqa: F401
    except ImportError:
        print("vrating needs numpy:\n\n    pip install -r requirements.txt\n", file=sys.stderr)
        return 1

    from .web import server

    port = _free_port(int(os.environ.get("VRATING_PORT", "8770")))
    url = f"http://127.0.0.1:{port}/"
    if handles and not from_env:
        # Every account, not just the first: the page replays them as one career. Handles
        # from .env are deliberately left out of the URL -- the page asks the server for
        # them instead and gets the list with renames already resolved.
        url += "#" + urllib.parse.quote(",".join(handles))

    say = lambda m: print(m, flush=True)   # unbuffered: this banner is the only feedback
    say(f"vrating → {url}")
    if handles:
        source = "from .env" if from_env else "from the command line"
        say(f"  {len(handles)} handle(s) {source}: {', '.join(handles)}")
        say("  warming them in the background…")
        threading.Thread(target=_warm, args=(handles,), daemon=True).start()
    else:
        say("  tip: put VRATING_HANDLES in .env, or pass a handle, to warm it up front")
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
