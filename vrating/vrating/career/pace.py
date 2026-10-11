"""How long you take on the problems you *do* solve.

The upsolve list answers "what can't I solve". This answers a different failure: bleeding time
on problems well within reach. A strong solver who takes eleven minutes on A has already lost
places before reaching the problem that decides the round, and nothing in a rating tells them.

The comparison is the same shape as the solve-rate curve -- the field is a labelled sample of
(rating, minutes-to-solve), so bin by rating, take the median per bin, and read it at the
rating you held that day. Median rather than mean: solve times have a long right tail from
people who opened the problem late, and one straggler should not move the bar.

Only solved problems count. An unsolved one has no time, and counting it as "slow" would
double-punish what the upsolve list already covers.
"""
from __future__ import annotations

import functools
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from ..rating import cf
from ..sources import archive, cf as src

WORKERS = int(os.environ.get("VRATING_WORKERS", "4"))
BIN = 200.0          # wider than the solve-rate bins: timings are noisier
MIN_PER_BIN = 30


@dataclass
class Split:
    contest_id: int
    contest_name: str
    index: str
    when: int
    minutes: float        # what it took you
    peer_minutes: float   # median for people at the rating you held then
    rating_then: int
    peers: int

    @property
    def ratio(self) -> float:
        return self.minutes / self.peer_minutes if self.peer_minutes else 1.0


@functools.lru_cache(maxsize=128)
def time_curves(contest_id: int):
    """Median minutes-to-solve against rating, per problem.

    Returns (bin centres, medians, counts) with NaN where a bin had too few solvers to say
    anything -- a problem only two people at your level solved has no meaningful median.
    """
    changes = src.rating_changes(contest_id)
    if changes is None:
        return None
    st = src.standings(contest_id)
    idx = {h: i for i, h in enumerate(st["handles"])}
    rows = [(h, r) for h, r in zip(changes["handles"], changes["old"]) if h in idx]
    if len(rows) < 200:
        return None

    prior = archive.prior_counts(contest_id)
    by_handle = {}
    if prior is not None and len(prior) == len(changes["handles"]):
        by_handle = dict(zip(changes["handles"], prior))

    ratings = np.array([float(r) + cf.internal_offset(int(by_handle.get(h, 99)), st["start"])
                        for h, r in rows])
    times = st["pr_time"][[idx[h] for h, _ in rows]] / 60.0     # minutes; -1/60 when unsolved
    order = np.argsort(ratings)
    ratings, times = ratings[order], times[order]

    centres, medians, counts = [], [], []
    lo = float(np.floor(ratings[0] / BIN) * BIN)
    i, n = 0, len(ratings)
    while i < n:
        hi = lo + BIN
        j = int(np.searchsorted(ratings, hi))
        while j - i < MIN_PER_BIN and j < n:
            hi += BIN
            j = int(np.searchsorted(ratings, hi))
        if j - i < MIN_PER_BIN:
            break
        block = times[i:j]
        row = []
        for k in range(block.shape[1]):
            solved = block[:, k][block[:, k] >= 0]
            row.append(float(np.median(solved)) if len(solved) >= MIN_PER_BIN else np.nan)
        centres.append((lo + hi) / 2.0)
        medians.append(row)
        counts.append(j - i)
        lo, i = hi, j
    if len(centres) < 2:
        return None
    return np.array(centres), np.array(medians), np.array(counts)


def _read(centres, medians, counts, rating, problem):
    """Median at a rating, ignoring bins with no usable sample."""
    col = medians[:, problem]
    ok = ~np.isnan(col)
    if ok.sum() < 2:
        return None, 0
    value = float(np.interp(rating, centres[ok], col[ok]))
    near = int(counts[int(np.argmin(np.abs(centres - rating)))])
    return value, near


def splits(entries, progress=None) -> list[Split]:
    """`entries` are career rows carrying `solved_at` -- your minutes per solved problem."""
    def curves_for(e):
        try:
            return time_curves(e["contest_id"])
        except src.CodeforcesError:
            return None

    pool = ThreadPoolExecutor(max_workers=WORKERS)
    out: list[Split] = []
    try:
        fitted = [pool.submit(curves_for, e) for e in entries]
        for n, e in enumerate(entries):
            if progress:
                progress(n, len(entries), str(e["contest_id"]))
            curves = fitted[n].result()
            if curves is None or not e.get("solved_at"):
                continue
            centres, medians, counts = curves
            st = src.standings(e["contest_id"])
            names = list(st["problem_index"])
            for index, seconds in e["solved_at"].items():
                if index not in names:
                    continue
                peer, near = _read(centres, medians, counts, e["rating_then"], names.index(index))
                if peer is None or peer <= 0:
                    continue
                out.append(Split(
                    contest_id=e["contest_id"], contest_name=e.get("name", ""),
                    index=index, when=e.get("start", 0),
                    minutes=seconds / 60.0, peer_minutes=peer,
                    rating_then=int(e["rating_then"]), peers=near))
    finally:
        pool.shutdown(wait=False)
    return out


def summary(items: list[Split]) -> dict:
    """The headline, plus a per-slot breakdown.

    Ratios are summarised by their median: a single problem you sat on for an hour should not
    decide the verdict.
    """
    if not items:
        return {"overall": None, "by_slot": [], "worst": []}
    overall = float(np.median([s.ratio for s in items]))
    slots: dict[str, list[Split]] = {}
    for s in items:
        slots.setdefault(s.index, []).append(s)
    by_slot = [{
        "index": k,
        "n": len(v),
        "ratio": float(np.median([x.ratio for x in v])),
        "minutes": float(np.median([x.minutes for x in v])),
        "peer_minutes": float(np.median([x.peer_minutes for x in v])),
    } for k, v in sorted(slots.items())]
    worst = sorted(items, key=lambda s: -s.ratio)[:10]
    return {"overall": overall, "by_slot": by_slot,
            "worst": [{"contest_id": s.contest_id, "contest_name": s.contest_name,
                       "index": s.index, "minutes": round(s.minutes, 1),
                       "peer_minutes": round(s.peer_minutes, 1),
                       "ratio": round(s.ratio, 2), "rating_then": s.rating_then,
                       "peers": s.peers} for s in worst]}
