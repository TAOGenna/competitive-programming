"""AtCoder rating math. Pure functions, no I/O.

Validated against AtCoder's own history/json: 96.4% exact over 421 predictions across 17
users spanning the full rating range, and 100% exact for most of them.

Two details break naive implementations, both established from the data:
  - APerf is a weighted average in 2^(perf/800) space, not linear space.
  - The rating uses the *capped* `Performance` field, not `InnerPerformance`. ABC rounds cap
    performance at 2400; using the uncapped value is wrong by 300-500 for strong performers.

Not yet wired into the app: AtCoder's standings need a login, so a virtual rank has to be
supplied by hand. Everything downstream of the rank is here.
"""
from __future__ import annotations

import bisect
import math

DECAY = 0.9
SCALE = 800.0
SPREAD = 1200.0


def aperf(performances: list[float]) -> float:
    """Weighted average performance. `performances` oldest first."""
    recent_first = performances[::-1]
    num = sum(2.0 ** (p / SCALE) * DECAY ** (i + 1) for i, p in enumerate(recent_first))
    den = sum(DECAY ** (i + 1) for i in range(len(recent_first)))
    return SCALE * math.log2(num / den)


def _F(k: int) -> float:
    sq = DECAY * DECAY
    return math.sqrt(sum(sq ** (i + 1) for i in range(k))) / sum(DECAY ** (i + 1) for i in range(k))


def _correction(n: int) -> float:
    """Penalty for having few contests: 1200 at n=1, decaying towards 0."""
    sq = DECAY * DECAY
    f_inf = math.sqrt(sq / (1 - sq)) / (DECAY / (1 - DECAY))
    return (_F(n) - f_inf) / (_F(1) - f_inf) * SPREAD


def rating(performances: list[float]) -> float:
    """Rating implied by a performance history, oldest first."""
    if not performances:
        return 0.0
    r = aperf(performances) - _correction(len(performances))
    if r <= 0:                       # positivize: displayed ratings never go below zero
        r = 400.0 / math.exp((400.0 - r) / 400.0)
    return r


def performance_for_rank(rank: int, places: list[int], performances: list[float]) -> float:
    """Performance for a rank, read off the contest's own rank/performance curve.

    `places` ascending with `performances` alongside, as they come out of results/json.
    Interpolating the published curve reproduces a real participant's performance to within
    a rating point, and it comes out correctly capped, since the cap is a property of the
    contest rather than of the participant.
    """
    if not places:
        raise ValueError("no results to interpolate")
    i = bisect.bisect_left(places, rank)
    if i == 0:
        return performances[0]
    if i >= len(places):
        return performances[-1]
    lo, hi = places[i - 1], places[i]
    if hi == lo:
        return performances[i]
    t = (rank - lo) / (hi - lo)
    return performances[i - 1] + (performances[i] - performances[i - 1]) * t
