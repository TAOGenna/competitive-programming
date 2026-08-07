"""Fill the cache for every rated contest, once.

This is the difference between a toy on localhost and something that serves other people.
Codeforces allows roughly one request per second *per IP*, not per user -- so on a cold cache
every visitor's replay queues behind every other visitor's. With standings cached, a request
makes only 2-3 API calls (that user's own submissions and rating history) and everything else
is read from disk.

    ~1780 rated contests                         ~25 minutes, once
    downloaded                                   ~9.5 MB per contest, ~16 GB total
    kept on disk                                 ~200 KB per contest, ~600 MB all in
    per-visitor API calls afterwards             2-3

A standings response is ~9.5 MB and takes ~3.7 s to transfer, so a serial run is bound by
bandwidth rather than by the rate limit -- about two hours. The limit governs how often a
request may be *issued*, not how many may be in flight, so a few workers overlap their
transfers while requests still leave one second apart. That is the difference between two
hours and twenty-five minutes; it does not send Codeforces requests any faster.

At 100 visitors an hour that is ~300 calls/hour, or 0.08 req/s -- comfortably inside the
limit, where an unwarmed cache would blow through it with a single user.

Resumable: anything already cached is skipped. Safe to re-run to pick up new contests.

For a single user there is no reason to warm the whole archive: pass handles and only the
contests those accounts have actually sat are fetched.

    python3 -m vrating.sources.prewarm                 # everything, for a public instance
    python3 -m vrating.sources.prewarm your_handle     # just yours, minutes not hours
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import archive
from . import cf as src


WORKERS = int(os.environ.get("VRATING_PREWARM_WORKERS", "4"))


def prewarm(log=print, limit: int | None = None, workers: int = WORKERS) -> tuple[int, int]:
    contests = [c for c in src.contest_list() if c["phase"] == "FINISHED"]
    contests.sort(key=lambda c: -c["startTimeSeconds"])
    if limit:
        contests = contests[:limit]

    counts = {"done": 0, "skipped": 0, "seen": 0}
    started = time.monotonic()

    def one(c):
        cid = c["id"]
        try:
            if src.rating_changes(cid) is None:
                counts["skipped"] += 1        # unrated: nothing to serve from it
            else:
                src.standings(cid)
                counts["done"] += 1
        except src.CodeforcesError:
            counts["skipped"] += 1
        except Exception as exc:                       # noqa: BLE001 - keep going
            counts["skipped"] += 1
            log(f"  skip {cid}: {type(exc).__name__} {exc}")
        counts["seen"] += 1
        n = counts["seen"]
        if n % 50 == 0:
            rate = n / max(time.monotonic() - started, 1e-9)
            left = (len(contests) - n) / max(rate, 1e-9)
            log(f"  {n}/{len(contests)} cached={counts['done']} "
                f"skipped={counts['skipped']} eta {left / 60:.0f} min")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, contests))
    return counts["done"], counts["skipped"]


def prewarm_for(handles, log=print, workers: int = WORKERS) -> tuple[int, int]:
    """Warm only the contests these handles have actually sat.

    Running this for yourself is a couple of hundred contests, not eighteen hundred -- a few
    minutes and a few tens of MB instead of half an hour and 16 GB. Everything the app can
    show you concerns rounds you took part in, so the rest of the archive earns nothing until
    somebody else visits.
    """
    from ..career import engine, upsolve

    wanted: set[int] = set()
    for handle in handles:
        for p in engine.virtual_participations([handle]):
            wanted.add(p["contest_id"])
        try:
            for h in src.user_rating(handle):
                wanted.add(h["contestId"])
        except src.CodeforcesError:
            pass
    log(f"{len(handles)} handle(s) -> {len(wanted)} contests to warm")

    counts = {"done": 0, "skipped": 0}

    def one(cid):
        try:
            if src.rating_changes(cid) is None:
                counts["skipped"] += 1
            else:
                src.standings(cid)
                counts["done"] += 1
        except Exception:                                  # noqa: BLE001 - keep going
            counts["skipped"] += 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, sorted(wanted)))
    return counts["done"], counts["skipped"]


def main():
    log = lambda m: print(m, flush=True)
    handles = [a for a in sys.argv[1:] if not a.startswith("-")]
    if handles:
        log(f"warming just the contests {', '.join(handles)} have sat…")
        done, skipped = prewarm_for(handles, log)
        log(f"cached {done} contests, skipped {skipped}")
        log("building the prior-contest index…")
        archive.build_index(log)
        log("done")
        return
    log("warming rating changes and standings (resumable; ctrl-c is safe)…")
    done, skipped = prewarm(log)
    log(f"standings cached for {done} contests, {skipped} skipped")
    log("building the prior-contest index…")
    archive.build_index(log)
    log("done — the server will now serve almost everything from disk")


if __name__ == "__main__":
    sys.exit(main())
