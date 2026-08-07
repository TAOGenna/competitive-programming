"""Which problems you should have solved.

The question: of the problems you left behind, which ones do people at your level routinely
get? A failure there is a real gap; a failure on something almost nobody solves is not.

Method. For every problem, the field gives a labelled sample: each rated participant's
rating, and whether they solved it. Bin by rating, take the solve fraction per bin, force the
result non-decreasing (a higher rating cannot make you less likely to solve something --
isotonic regression via pool-adjacent-violators), then read the curve. That is a calibrated
probability: "78% of people at your level solved this".

Which rating to read it at. The curve is built from one contest's field, so its rating axis
is that contest's, at that date. Codeforces ratings drift -- measurably 150-190 points between
2023 and 2026 alone -- so a 2018 field's 1600 is not a 2026 1600. Reading an old curve at
your *current* rating silently compares across a moving axis. It is read at the rating you
held when you sat the round, which keeps the whole comparison contemporaneous.

That answers "where did I underperform my peers". Whether a problem is worth your time *now*
is a different question on a different axis, and is answered separately by Codeforces' own
problem difficulty, which is global rather than per-contest.

Why not a rank neighbourhood. Ranking within +-300 places is the intuitive version of the
same idea, but rank mixes skill with that day's form -- a bad round seats you among weaker
people, lowering the bar exactly when you want it held. It also throws away the field: a 600
person slice of a 20,000 person contest estimates the same quantity from 3% of the data.
Fitting against rating uses everyone and answers the question actually being asked.

Ranking. Failing a problem with solve probability p carries surprisal -log(1-p), which is
monotone in p, so ordering by p *is* ordering by how surprising the miss was. Difficulty is
reported alongside rather than folded in, because "what did I miss" and "what is worth
learning" are different questions and merging them into one score answers neither.
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
BIN = 100.0          # rating bin width
MIN_PER_BIN = 25     # below this a bin is merged into its neighbour
DEFAULT_FLOOR = 0.5  # only surface problems the majority of your peers solved


@dataclass
class Suggestion:
    contest_id: int
    index: str
    name: str
    contest_name: str
    when: int
    solve_rate: float     # among people at the level you were then
    peers: int            # sample size in that rating neighbourhood
    rating_then: int      # the rating the comparison was made at
    difficulty: int | None
    tags: list
    attempted: bool       # you submitted and did not get it


def _isotonic(values, weights):
    """Nearest non-decreasing fit (pool-adjacent-violators), weighted by bin population."""
    blocks: list[list[float]] = []          # [value, weight, count]
    for v, w in zip(values, weights):
        blocks.append([float(v), float(w), 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, c2 = blocks.pop()
            v1, w1, c1 = blocks.pop()
            tot = w1 + w2
            blocks.append([(v1 * w1 + v2 * w2) / tot if tot else v1, tot, c1 + c2])
    out = []
    for v, _, c in blocks:
        out.extend([v] * c)
    return np.array(out)


@functools.lru_cache(maxsize=128)
def solve_curves(contest_id: int):
    """Per problem, a monotone solve-rate curve over rating.

    Returns (centres, rates) where rates[j] aligns with the contest's problem list, or None
    when the contest cannot supply a usable sample.
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
    prior_by = {}
    if prior is not None and len(prior) == len(changes["handles"]):
        prior_by = dict(zip(changes["handles"], prior))

    ratings = np.array([float(r) + cf.internal_offset(int(prior_by.get(h, 99)), st["start"])
                        for h, r in rows])
    solved = st["pr_time"][[idx[h] for h, _ in rows]] >= 0      # bestSubmissionTime present

    order = np.argsort(ratings)
    ratings, solved = ratings[order], solved[order]

    # bins of BIN rating, merged forward until each holds MIN_PER_BIN people
    centres, rates, counts = [], [], []
    lo = float(np.floor(ratings[0] / BIN) * BIN)
    i = 0
    n = len(ratings)
    while i < n:
        hi = lo + BIN
        j = int(np.searchsorted(ratings, hi))
        while j - i < MIN_PER_BIN and j < n:
            hi += BIN
            j = int(np.searchsorted(ratings, hi))
        if j - i < MIN_PER_BIN:
            break
        centres.append((lo + hi) / 2.0)
        rates.append(solved[i:j].mean(axis=0))
        counts.append(j - i)
        lo, i = hi, j
    if len(centres) < 2:
        return None

    centres = np.array(centres)
    counts = np.array(counts, float)
    rates = np.vstack(rates)                                   # bins x problems
    monotone = np.column_stack([_isotonic(rates[:, j], counts) for j in range(rates.shape[1])])
    return centres, monotone, counts


@functools.lru_cache(maxsize=1)
def _problem_meta():
    """11k problems; parsed once per process rather than once per request."""
    out = {}
    for p in src.problemset():
        out[(p["contestId"], p["index"])] = p
    return out


def suggest(rating_now: float, participations, floor: float = DEFAULT_FLOOR,
            already_solved=frozenset(), progress=None) -> list[Suggestion]:
    """`participations` is [{contest_id, unsolved, attempted, rating_then}].

    Each round is judged against the rating you held when you sat it -- see the module note
    on why reading an old curve at today's rating would compare across a drifting axis.
    `rating_now` is used only to say how a problem sits relative to you today.

    `already_solved` holds (contestId, index) pairs you have since upsolved; they are dropped,
    since a list that keeps recommending finished work is worse than no list.
    """
    meta = _problem_meta()
    out: list[Suggestion] = []

    # Each round's solve curves are independent; fit them all at once, then walk in order.
    def curves_for(p):
        try:
            return solve_curves(p["contest_id"])
        except src.CodeforcesError:
            return None
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        fitted = [pool.submit(curves_for, p) for p in participations]
        for n, p in enumerate(participations):
            if progress:
                progress(n, len(participations), str(p["contest_id"]))
            if not p["unsolved"]:
                continue
            curves = fitted[n].result()
            if curves is None:
                continue
            centres, monotone, counts = curves
            st = src.standings(p["contest_id"])
            changes = src.rating_changes(p["contest_id"])
            rating_then = float(p.get("rating_then") or rating_now)
            near = int(counts[int(np.argmin(np.abs(centres - rating_then)))])

            for index in p["unsolved"]:
                if index not in st["problem_index"]:
                    continue
                key = (p["contest_id"], index)
                if key in already_solved:
                    continue
                j = list(st["problem_index"]).index(index)
                rate = float(np.interp(rating_then, centres, monotone[:, j]))
                if rate < floor:
                    continue
                info = meta.get(key, {})
                out.append(Suggestion(
                    contest_id=p["contest_id"], index=index,
                    name=info.get("name", index),
                    contest_name=changes["name"] if changes else str(p["contest_id"]),
                    when=st["start"],
                    solve_rate=rate, peers=near,
                    rating_then=int(round(rating_then)),
                    difficulty=info.get("rating"),
                    tags=info.get("tags", []),
                    attempted=index in p.get("attempted", []),
                ))
    finally:
        pool.shutdown(wait=False)

    out.sort(key=lambda s: (-s.solve_rate, -(s.difficulty or 0)))
    return out


def by_tag(items: list[Suggestion]) -> list[dict]:
    """Where the rust is. A tag you keep missing says more than any single problem."""
    counts: dict[str, list[float]] = {}
    for s in items:
        for t in s.tags:
            counts.setdefault(t, []).append(s.solve_rate)
    rows = [{"tag": t, "count": len(v), "mean_rate": sum(v) / len(v)} for t, v in counts.items()]
    rows.sort(key=lambda r: (-r["count"], -r["mean_rate"]))
    return rows


def history(handles, virtual_ratings=None, prefetched=None, progress=None):
    """Every round these accounts have sat -- real and virtual -- and what was left unsolved.

    Each round carries `rating_then`: the rating you actually held when you sat it, which is
    what the peer comparison must be made against. For real rounds that is the rating
    Codeforces recorded; for virtual ones it is the rating your virtual career stood at.

    Real rounds need no submission fetch: the participant's own row in the standings already
    records which problems they solved and how many attempts they burned.

    `prefetched` lets the browser supply the per-user data it has already pulled from
    Codeforces itself -- {handle: {virtual, solved, real, ratings}} -- so this makes no API
    calls at all. See vrating.web.server for why that is worth doing.
    """
    from ..rating import scoring
    if isinstance(handles, str):
        handles = [handles]

    solved_since: set[tuple] = set()
    virtual: dict[int, dict] = {}
    real: dict[int, str] = {}
    real_rating: dict[int, float] = {}
    virtual_ratings = virtual_ratings or {}

    for handle in handles:
        have = (prefetched or {}).get(handle)
        if have is not None:
            for cid, old in (have.get("ratings") or {}).items():
                real_rating[int(cid)] = float(old)
            for cid, index in have.get("solved") or []:
                solved_since.add((cid, index))
            for cid in have.get("real") or []:
                real.setdefault(int(cid), handle)
            for s in have.get("virtual") or []:
                cid = s.get("contestId")
                virtual.setdefault(cid, {"contest_id": cid, "handle": handle, "subs": []})
                if virtual[cid]["handle"] == handle:
                    virtual[cid]["subs"].append(s)
            continue

        try:
            for h in src.user_rating(handle):
                real_rating[h["contestId"]] = float(h["oldRating"])
        except src.CodeforcesError:
            pass
        for s in src.user_submissions(handle):
            cid, index = s.get("contestId"), s["problem"]["index"]
            if s.get("verdict") == "OK":
                solved_since.add((cid, index))
            kind = s["author"].get("participantType")
            if kind == "VIRTUAL":
                virtual.setdefault(cid, {"contest_id": cid, "handle": handle, "subs": []})
                if virtual[cid]["handle"] == handle:
                    virtual[cid]["subs"].append(s)
            elif kind == "CONTESTANT":
                real.setdefault(cid, handle)

    out = []
    seen = set()
    for cid, v in virtual.items():
        # gym and unrated rounds have no rated field to compare against, and asking for their
        # standings is a wasted round trip -- rating_changes already answers this from disk
        if src.rating_changes(cid) is None:
            continue
        try:
            st = src.standings(cid)
        except src.CodeforcesError:
            continue
        res = scoring.problem_results(v["subs"], st["problem_index"], st["duration"])
        out.append({"contest_id": cid,
                    "rating_then": virtual_ratings.get(cid),
                    "unsolved": [str(i) for i in st["problem_index"] if not res[i].solved],
                    "attempted": [str(i) for i in st["problem_index"]
                                  if not res[i].solved and res[i].rejects > 0]})
        seen.add(cid)

    for cid, handle in real.items():
        if cid in seen or src.rating_changes(cid) is None:
            continue
        try:
            st = src.standings(cid)
        except src.CodeforcesError:
            continue
        if handle not in st["handles"]:
            continue
        i = st["handles"].index(handle)
        times, rejects = st["pr_time"][i], st["pr_rejects"][i]
        out.append({"contest_id": cid,
                    "rating_then": real_rating.get(cid),
                    "unsolved": [str(x) for k, x in enumerate(st["problem_index"]) if times[k] < 0],
                    "attempted": [str(x) for k, x in enumerate(st["problem_index"])
                                  if times[k] < 0 and rejects[k] > 0]})
    return out, solved_since
