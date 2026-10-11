"""The rating archive: how many rated contests every handle had completed, at every point.

Why this exists. Codeforces reports a provisional account's *displayed* rating, which for its
first six rated contests sits below the internal rating the calculator actually uses. In a
Div. 2 field a large slice of the seed input is therefore wrong. The only way to recover the
internal rating is to know how many rated contests each participant had already sat -- which
is not exposed anywhere, but is derivable by walking every contest's rating changes in order.

Measured effect of using it (median absolute delta error, with calibration in both cases):

    rating band     calibration only    + internal ratings
    below 1200          9.5 - 13.9              1.0
    1200-1600            3.7 - 4.0              0.8
    1600-2000            1.6 - 1.8              1.0

Building it costs one pass over ~2100 contests at the API's ~1 req/s. Everything degrades
gracefully without it: `prior_counts` returns None and callers fall back to calibration alone.
"""
from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np

from . import cf as src

PRIOR_DIR = src.DATA / "prior"


def prior_counts(contest_id: int) -> np.ndarray | None:
    """Rated contests completed before this one, aligned with rating_changes()['handles']."""
    path = PRIOR_DIR / f"{contest_id}.npy"
    if not path.exists():
        return None
    return np.load(path)


def is_built() -> bool:
    return PRIOR_DIR.exists() and any(PRIOR_DIR.iterdir())


def fetch_all(log=print) -> None:
    """Download every finished contest's rating changes. Resumable; skips what is cached."""
    contests = [c for c in src.contest_list() if c["phase"] == "FINISHED"]
    contests.sort(key=lambda c: c["startTimeSeconds"])
    for i, c in enumerate(contests):
        src.rating_changes(c["id"])
        if (i + 1) % 100 == 0:
            log(f"  fetched {i + 1}/{len(contests)}")


def build_index(log=print) -> int:
    """Walk the archive in chronological order and snapshot per-contest prior counts."""
    PRIOR_DIR.mkdir(parents=True, exist_ok=True)
    contests = [c for c in src.contest_list() if c["phase"] == "FINISHED"]
    contests.sort(key=lambda c: c["startTimeSeconds"])

    seen: dict[str, int] = defaultdict(int)
    written = 0
    for c in contests:
        changes = src.rating_changes(c["id"])
        if changes is None:
            continue
        handles = changes["handles"]
        np.save(PRIOR_DIR / f"{c['id']}.npy",
                np.array([seen[h] for h in handles], np.int16))
        written += 1
        for h in handles:
            seen[h] += 1
    log(f"indexed {written} contests, {len(seen)} handles")
    return written


def main():
    log = lambda m: print(m, flush=True)
    log("fetching rating changes (resumable, ~1 req/s on a cold cache)…")
    fetch_all(log)
    log("building prior-contest index…")
    build_index(log)
    log("done — contest preparation will now reconstruct internal ratings")


if __name__ == "__main__":
    sys.exit(main())
