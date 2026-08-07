"""Codeforces rating math. Pure functions, no I/O.

Algorithm follows Mirzayanov's published system (codeforces.com/blog/entry/20762) with the
corrections that make it match production, as established in Carrot/TLE:
worst-rank-in-tie-group, trunc toward zero, binary search over [2, MAX] returning lo-1.

Validated against official deltas: >=98% within +-1 on Div. 1 fields, 2023-2026.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MIN_R, MAX_R = -500, 6000
NR = MAX_R - MIN_R          # number of grid points
DEFAULT_RATING = 1400       # effective rating of an account with no rated contests

# Displayed rating is below internal rating until an account has six rated contests.
# Promotions sum to exactly 1400 (codeforces.com/blog/entry/77890).
PROMOTIONS = (500, 350, 250, 150, 100, 50)

# Codeforces introduced the hidden-internal-rating scheme with round 1360. Before it, a new
# account simply started at 1500 and its displayed rating was its real one. Dated from the
# rating archive: contests before this show no participants with oldRating == 0, and bulk
# zeros appear from this round onwards.
NEW_ACCOUNT_RULE_START = 1590300000   # 2020-05-24
LEGACY_START_RATING = 1500


def uses_new_account_rule(contest_start_seconds: int) -> bool:
    return contest_start_seconds >= NEW_ACCOUNT_RULE_START


def internal_offset(prior_contests: int, contest_start_seconds: int) -> int:
    """Amount to add to a displayed rating to recover the internal one."""
    if not uses_new_account_rule(contest_start_seconds):
        return 0
    if prior_contests >= len(PROMOTIONS):
        return 0
    return DEFAULT_RATING - sum(PROMOTIONS[:prior_contests])


def promotion(prior_contests: int, contest_start_seconds: int) -> int:
    """Displayed-rating bump granted on top of the delta while an account is provisional."""
    if not uses_new_account_rule(contest_start_seconds):
        return 0
    if prior_contests >= len(PROMOTIONS):
        return 0
    return PROMOTIONS[prior_contests]


def _elo(diff):
    """P(a participant rated `diff` above loses to one at the reference rating)."""
    return 1.0 / (1.0 + np.power(10.0, np.asarray(diff, dtype=float) / 400.0))


def _fftconvolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    out = np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)
    return out[:n]


@dataclass
class Field:
    """A contest's rated field, prepared once for cheap repeated queries.

    `seed_grid[r - MIN_R]` is the expected rank of a non-participant rated r.
    """

    ratings: np.ndarray      # effective (internal) old ratings of the scored subset
    points: np.ndarray
    penalty: np.ndarray
    seed_grid: np.ndarray
    size_rated: int = 0      # everyone the contest rated, scored or not

    @property
    def size(self) -> int:
        return len(self.ratings)

    def seed(self, rating, exclude_rating=None):
        """Expected rank of a contestant rated `rating`.

        `exclude_rating` removes one field member — use it for participants who are
        themselves in the field. Leave it None for someone inserted from outside.
        Vectorized over both arguments.
        """
        idx = np.clip(np.rint(rating).astype(int) - MIN_R, 0, NR - 1)
        s = self.seed_grid[idx]
        if exclude_rating is None:
            return s
        return s - _elo(np.asarray(rating, float) - np.asarray(exclude_rating, float))

    def rank_of(self, points: float, penalty: float) -> int:
        """Rank this score would take in the field, using CF ordering and worst-rank ties.

        Worst-rank matches how the rating calculator groups ties.
        """
        better = int(np.sum((self.points > points) | ((self.points == points) & (self.penalty < penalty))))
        tied = int(np.sum((self.points == points) & (self.penalty == penalty)))
        return better + tied + 1


def build_field(ratings, points, penalty, seed_ratings=None) -> Field:
    """Prepare a contest's field.

    `seed_ratings` is every rated participant, which is what the expected-rank calculation
    must run over. It can be a superset of `ratings`: some contests rate far more people than
    their standings expose, and the seed would be badly wrong if built from the visible
    subset alone. Defaults to `ratings` when the two coincide.
    """
    ratings = np.rint(np.asarray(ratings, float)).astype(int)
    seed_source = ratings if seed_ratings is None else np.rint(np.asarray(seed_ratings, float)).astype(int)
    counts = np.bincount(np.clip(seed_source - MIN_R, 0, NR - 1), minlength=NR).astype(float)
    kernel = _elo(np.arange(-NR, NR + 1))
    seed_grid = _fftconvolve(kernel, counts)[NR : NR + NR] + 1.0
    return Field(
        ratings=ratings.astype(float),
        points=np.asarray(points, float),
        penalty=np.asarray(penalty, float),
        seed_grid=seed_grid,
        size_rated=len(seed_source),
    )


def _need_rating(field: Field, target_seed, self_rating) -> np.ndarray:
    """Last rating whose seed is >= target_seed. Vectorized binary search over all inputs.

    `self_rating` may be None for contestants inserted from outside the field.
    """
    target_seed = np.asarray(target_seed, float)
    if self_rating is not None:
        self_rating = np.asarray(self_rating, float)
    lo = np.full(target_seed.shape, 2, dtype=np.int64)
    hi = np.full(target_seed.shape, MAX_R, dtype=np.int64)
    while np.any(lo < hi):
        mid = (lo + hi) // 2
        below = field.seed(mid, self_rating) < target_seed
        hi = np.where(below, mid, hi)
        lo = np.where(below, lo, mid + 1)
    return lo - 1


def _reassign_ranks(points: np.ndarray, penalty: np.ndarray) -> np.ndarray:
    """Rank each row, giving every member of a tie group the group's worst rank."""
    order = np.lexsort((penalty, -points))
    p, q = points[order], penalty[order]
    starts_group = np.r_[True, (p[1:] != p[:-1]) | (q[1:] != q[:-1])]
    group = np.cumsum(starts_group) - 1
    # elements are grouped contiguously, so this lands on the group's worst 1-indexed rank
    out = np.empty(len(order), dtype=np.int64)
    out[order] = np.searchsorted(group, group, side="right")
    return out


def raw_deltas(field: Field, ranks: np.ndarray) -> np.ndarray:
    """Deltas before the two zero-sum adjustments."""
    own_seed = field.seed_grid[np.clip(field.ratings.astype(int) - MIN_R, 0, NR - 1)] - 0.5
    mid = np.sqrt(ranks * own_seed)
    need = _need_rating(field, mid, field.ratings)
    return np.trunc((need - field.ratings) / 2.0)


def adjustments(field: Field, deltas: np.ndarray) -> int:
    """The two population-level corrections, returned as a single additive constant.

    Both are applied uniformly to every participant, so they collapse to one number.
    """
    n = field.size
    inc1 = math.trunc(-float(deltas.sum()) / n) - 1
    d = deltas + inc1
    by_rating = np.argsort(-field.ratings, kind="stable")
    z = min(4 * round(math.sqrt(n)), n)
    inc2 = min(max(math.trunc(-float(d[by_rating[:z]].sum()) / z), -10), 0)
    return inc1 + inc2


def field_deltas(field: Field) -> np.ndarray:
    """Official-style deltas for every participant in the field."""
    ranks = _reassign_ranks(field.points, field.penalty)
    d = raw_deltas(field, ranks)
    return d + adjustments(field, d)


def delta_for(field: Field, rating: float, rank: int, adjustment: int) -> int:
    """Delta for a single contestant inserted into the field. O(log MAX_R).

    `adjustment` is the field's population correction, computed once per contest.
    """
    seed = float(field.seed(np.array([float(rating)]))[0])
    mid = math.sqrt(rank * seed)
    need = int(_need_rating(field, np.array([mid]), None)[0])
    return int(math.trunc((need - rating) / 2.0)) + adjustment
