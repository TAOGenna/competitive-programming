"""Prepare a historical contest so a virtual result can be scored against it cheaply.

Preparation is the expensive part (build the seed grid, compute the field's deltas, fit the
calibration curve). It is done once per contest and cached; after that, inserting a
contestant costs a fraction of a millisecond.

Accuracy comes from two independent corrections:

  1. Internal ratings. A provisional account's displayed rating hides the rating Codeforces
     actually calculates with. `sources.archive` recovers it from the full rating history.
  2. Calibration. Codeforces publishes every participant's real delta, so the residual
     between our delta and the official one is observable. Fitting it against rating and
     adding it back absorbs whatever the first correction missed.

Median absolute delta error for established accounts, by rating band:

    band          raw    + calibration    + internal ratings
    below 1200   40-57        9.5-13.9            1.0
    1200-1600    12-25          3.7-4.0           1.0
    1600-2000     3-14          1.6-1.8           1.0
    2000+         1-11          0.5-1.0           0.0

Both degrade gracefully: without the archive, calibration alone still holds the middle bands
to a few points, and `confidence()` reports the weaker tier.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass

import numpy as np

from ..rating import cf, scoring
from ..sources import archive, cf as src

BIN_WIDTH = 100.0
MIN_PER_BIN = 8


@dataclass
class Prepared:
    contest_id: int
    name: str
    start: int
    duration: int
    type: str
    problem_index: list
    problem_points: np.ndarray
    field: cf.Field
    adjustment: int
    calib_x: np.ndarray
    calib_y: np.ndarray
    rated_min: float
    rated_max: float
    exact_field: bool = False   # internal ratings reconstructed from the archive
    matched: float = 1.0        # share of the rated field found in the standings
    official_rank: np.ndarray | None = None   # set only when standings rows are missing

    def correction(self, rating: float) -> float:
        if len(self.calib_x) < 2:
            return 0.0
        return float(np.interp(float(rating), self.calib_x, self.calib_y))

    def rank_for(self, points: float, penalty: float) -> int:
        """Where this score would place, on the contest's official rank scale.

        Div. 3 and Div. 4 rounds rate far more people than their standings expose -- contest
        1971 rated 23,309 but serves 12,040 rows, missing even the winner. Ranking against
        the visible half would flatter the result by roughly a factor of two, so when rows
        are missing the position is mapped back onto the official ranks we do know.
        """
        if self.official_rank is None:
            return self.field.rank_of(points, penalty)
        better = int(np.sum((self.field.points > points)
                            | ((self.field.points == points) & (self.field.penalty < penalty))))
        ranks = self.official_rank
        if better == 0:
            return 1
        if better >= len(ranks):
            return int(ranks[-1]) + 1
        # the score lands between two known participants; the unseen ones sit in that gap
        return int(round((ranks[better - 1] + 1 + ranks[better]) / 2))

    def delta_for(self, rating: float, rank: int) -> int:
        raw = cf.delta_for(self.field, rating, rank, self.adjustment)
        return int(round(raw + self.correction(rating)))

    def performance(self, rank: int) -> int:
        """Rating at which this rank would produce no change. Monotone, so bisect."""
        lo, hi = cf.MIN_R, cf.MAX_R
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.delta_for(mid, rank) >= 0:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def is_rated_for(self, rating: float) -> bool:
        return self.rated_min - 1e-9 <= rating <= self.rated_max + 1e-9

    def confidence(self, rating: float) -> str:
        """How much to trust a delta at this rating. Tiers are set from measured p90 error
        against ~3500 established accounts across five contests:

            exact       p90 <= 3     archive present and rating >= 1600, or a Div. 1 field
            corrected   p90 <= 6     archive present, lower ratings
            approximate               no archive, or too little of the field to place a score

        A partially served standings is *not* a reason to lose confidence: ranks are mapped
        back onto the official scale, and a Div. 4 round serving half its rows measures the
        same as one serving all of them. Only a field too sparse to interpolate is doubtful.
        """
        if len(self.calib_x) < 2 or self.matched < 0.3:
            return "approximate"
        below_sample = rating < self.calib_x[0] - BIN_WIDTH
        if below_sample:
            return "approximate"
        if not self.exact_field:
            return "exact" if rating >= 2000 else "corrected"
        return "exact" if rating >= 1600 else "corrected"


def _fit_calibration(ratings: np.ndarray, residual: np.ndarray):
    edges = np.arange(cf.MIN_R, 4001, BIN_WIDTH)
    xs, ys = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (ratings >= lo) & (ratings < hi)
        if m.sum() >= MIN_PER_BIN:
            xs.append((lo + hi) / 2.0)
            ys.append(float(np.median(residual[m])))
    return np.array(xs), np.array(ys)


# Preparation is ~30 ms and a career touches the same contests repeatedly across visitors.
# Bounded so memory stays flat: ~0.6 MB per entry (seed grid plus the field), so the default
# 256 settles around 200 MB. Lower VRATING_CACHED_CONTESTS on a small box.
@functools.lru_cache(maxsize=int(os.environ.get("VRATING_CACHED_CONTESTS", "256")))
def prepare(contest_id: int) -> Prepared | None:
    """Build everything needed to score a virtual result. None if the contest was unrated."""
    try:
        changes = src.rating_changes(contest_id)
        if changes is None:
            return None
        st = src.standings(contest_id)
    except src.CodeforcesError:
        # One contest the API will not serve (gym, removed, still running) must not take the
        # whole career down with it -- the round is simply skipped.
        return None

    points = dict(zip(st["handles"], st["points"]))
    penalty = dict(zip(st["handles"], st["penalty"]))
    keep = np.array([h in points for h in changes["handles"]])
    if keep.sum() < 50:
        return None
    handles = [h for h, k in zip(changes["handles"], keep) if k]
    displayed = changes["old"][keep].astype(float)

    # Provisional accounts are calculated at a hidden internal rating. With the archive we
    # know exactly who they are; without it we fall back on calibration to absorb the bias.
    prior_all = archive.prior_counts(contest_id)
    if prior_all is not None and len(prior_all) != len(changes["handles"]):
        prior_all = None
    prior = prior_all[keep] if prior_all is not None else None
    if prior is not None:
        ratings = displayed + np.array(
            [cf.internal_offset(int(k), st["start"]) for k in prior], float)
        bonus = np.array([cf.promotion(int(k), st["start"]) for k in prior], float)
        exact_field = True
    else:
        ratings, bonus, exact_field = displayed, 0.0, False

    # Seed over every rated participant, whose ratings we always have, even where the
    # standings withhold their scores.
    all_internal = changes["old"].astype(float)
    if prior_all is not None:
        all_internal = all_internal + np.array(
            [cf.internal_offset(int(k), st["start"]) for k in prior_all], float)
    field = cf.build_field(ratings, [points[h] for h in handles], [penalty[h] for h in handles],
                           seed_ratings=all_internal)

    matched = float(keep.mean())
    official_rank = None
    if matched < 0.98:
        order = np.lexsort((field.penalty, -field.points))
        official_rank = changes["rank"][keep][order].astype(np.int64)
        # recomputing ranks over a partial field would put everyone far too high, so
        # calibrate against the ranks Codeforces actually awarded
        ranks = changes["rank"][keep].astype(float)
    else:
        ranks = cf._reassign_ranks(field.points, field.penalty)
    raw = cf.raw_deltas(field, ranks)
    adjustment = cf.adjustments(field, raw)
    official = (changes["new"][keep] - changes["old"][keep]).astype(float)
    # Calibrate against displayed rating: that is the axis a caller will look themselves up on.
    calib_x, calib_y = _fit_calibration(displayed, official - (raw + adjustment + bonus))

    old = displayed
    return Prepared(
        contest_id=contest_id,
        name=changes["name"] or str(contest_id),
        start=st["start"],
        duration=st["duration"],
        type=st["type"],
        problem_index=st["problem_index"],
        problem_points=st["problem_points"],
        field=field,
        adjustment=adjustment,
        calib_x=calib_x,
        calib_y=calib_y,
        rated_min=float(old.min()),
        rated_max=float(old.max()),
        exact_field=exact_field,
        matched=matched,
        official_rank=official_rank,
    )


def score_submissions(prep: Prepared, submissions):
    """Returns (points, penalty, per-problem results) -- the results carry what was left
    unsolved, which is the list worth upsolving."""
    results = scoring.problem_results(submissions, prep.problem_index, prep.duration)
    points, penalty = scoring.score(results, prep.problem_points, prep.problem_index,
                                    prep.type, prep.duration)
    return points, penalty, results
