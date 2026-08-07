"""Chain virtual contests into a rating career.

The defining rule: contest n is scored against the rating you held after contest n-1 in the
*virtual* timeline, not your real rating. That is what makes this a parallel career rather
than a series of independent what-ifs.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from ..rating import cf
from ..sources import cf as src
from . import contest as contest_mod

START_RATING = 0          # displayed rating of a fresh account under the modern rule

# Preparing a contest is independent of every other contest; only the chaining is sequential.
# numpy drops the GIL for the FFT and the vectorized search, so threads genuinely help here.
WORKERS = int(os.environ.get("VRATING_WORKERS", "4"))


@dataclass
class Entry:
    contest_id: int
    name: str
    handle: str
    start: int
    rank: int
    field_size: int
    points: float
    penalty: float
    performance: int
    old_rating: int
    new_rating: int
    delta: int
    confidence: str
    rated: bool
    live: bool          # you actually competed in this one; the rest are virtual
    unsolved: list      # problem indexes left unsolved -- the upsolving list
    attempted: list     # of those, the ones you did submit to


def parse_handles(text: str) -> list[str]:
    """Split a handle list on commas or whitespace, preserving order, dropping repeats."""
    seen, out = set(), []
    for part in text.replace(",", " ").split():
        if part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    return out


def main_handle(handles: list[str]) -> str:
    """Whichever account has competed most -- its real rating is the meaningful comparison."""
    best, best_n = handles[0], -1
    for h in handles:
        try:
            n = len(src.user_rating(h))
        except Exception:
            n = 0
        if n > best_n:
            best, best_n = h, n
    return best


def real_curve(handle: str) -> list[dict]:
    """The handle's actual rating history, for comparison against the virtual one."""
    try:
        return [{"t": h["ratingUpdateTimeSeconds"], "rating": h["newRating"]}
                for h in src.user_rating(handle)]
    except Exception:
        return []


def group_virtual(subs_by_handle) -> list[dict]:
    """Group already-fetched submissions into sittings. See virtual_participations.

    Split out so the browser can do the fetching: user.status and user.rating are per-user
    endpoints that Codeforces serves with CORS, so a visitor can pull their own data against
    their own rate-limit budget, in parallel, instead of queueing behind everyone else.
    """
    by_contest: dict[int, dict] = {}
    for handle, subs in subs_by_handle:
        for s in subs:
            party = s["author"]
            if party.get("participantType") != "VIRTUAL":
                continue
            cid = s.get("contestId")
            started = party.get("startTimeSeconds", 0)
            cur = by_contest.get(cid)
            if cur is None or started < cur["started"]:
                by_contest[cid] = {"contest_id": cid, "started": started,
                                   "handle": handle, "submissions": []}
        for s in subs:
            party = s["author"]
            cid = s.get("contestId")
            cur = by_contest.get(cid)
            if (party.get("participantType") == "VIRTUAL" and cur is not None
                    and cur["handle"] == handle
                    and party.get("startTimeSeconds", 0) == cur["started"]):
                cur["submissions"].append(s)
    return sorted(by_contest.values(), key=lambda v: v["started"])


def real_participations(handles) -> list[dict]:
    """Rounds these accounts actually competed in, scored from their own standings row.

    No submission fetch is needed: the row records what they solved and how many attempts
    they burned, which is exactly what the rating calculation wants.
    """
    if isinstance(handles, str):
        handles = [handles]
    out = []
    for handle in handles:
        try:
            history = src.user_rating(handle)
        except src.CodeforcesError:
            continue
        for h in history:
            cid = h["contestId"]
            try:
                st = src.standings(cid)
            except src.CodeforcesError:
                continue
            if handle not in st["handles"]:
                continue
            i = st["handles"].index(handle)
            out.append({"contest_id": cid, "started": h["ratingUpdateTimeSeconds"],
                        "handle": handle, "submissions": [], "live": True,
                        "points": float(st["points"][i]), "penalty": float(st["penalty"][i])})
    return out


def merged_participations(handles) -> list[dict]:
    """Real and virtual rounds on one timeline, in the order they happened.

    The other framing -- virtual rounds alone, from scratch -- answers "what if only my
    practice counted", and on a long career that quietly discards a lot: once the from-scratch
    rating climbs past a division's ceiling, every later Div. 2 round becomes ineligible and
    contributes nothing. Merging answers "what if my practice had counted too", which is
    usually the question people mean, and no round goes to waste.
    """
    virtual = virtual_participations(handles)
    seen = {p["contest_id"] for p in virtual}
    real = [p for p in real_participations(handles) if p["contest_id"] not in seen]
    return sorted(virtual + real, key=lambda p: p["started"])


def virtual_participations(handles) -> list[dict]:
    """Every contest these accounts have virtual-participated in, oldest attempt first.

    Accepts one handle or several: people keep alt accounts, and the career they care about
    is the union. A contest sat on two accounts is kept once, at its earliest attempt --
    a rating career cannot count the same round twice, however many logins it took.

    The virtual start time -- not the contest's date -- sets the order, since that is when
    the round was actually sat.
    """
    if isinstance(handles, str):
        handles = [handles]
    return group_virtual([(h, src.user_submissions(h)) for h in handles])


def iter_career(handle, start_rating: int | None = None, participations=None,
                prepare=contest_mod.prepare):
    """Yield each virtual contest's outcome as it is computed.

    Streaming matters: on a cold cache each contest costs a couple of seconds of
    rate-limited API calls, and the page draws results as they land.
    """
    if participations is None:
        participations = virtual_participations(handle)

    if start_rating is None:
        # An account opened before round 1360 simply started at 1500.
        first = participations[0]["started"] if participations else 1 << 31
        start_rating = START_RATING if cf.uses_new_account_rule(first) else cf.LEGACY_START_RATING

    rating = float(start_rating)
    completed = 0

    # Fan the preparation out and consume in order, so the first round still streams the
    # moment it is ready while later rounds are already being computed. The pool must outlive
    # the loop: exiting a `with` block waits for every future, which would defeat streaming.
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        prepared = [pool.submit(prepare, p["contest_id"]) for p in participations]
        for p, future in zip(participations, prepared):
            prep = future.result()
            if prep is None:
                continue
            if p.get("points") is not None:      # a live round, already scored by the standings
                points, penalty, results = p["points"], p["penalty"], {}
            else:
                points, penalty, results = contest_mod.score_submissions(prep, p["submissions"])
            rank = prep.rank_for(points, penalty)

            internal = rating + cf.internal_offset(completed, prep.start)
            rated = prep.is_rated_for(internal)
            delta = prep.delta_for(internal, rank) if rated else 0
            promotion = cf.promotion(completed, prep.start) if rated else 0
            new_rating = rating + delta + promotion

            yield Entry(
                contest_id=p["contest_id"],
                name=prep.name,
                handle=p.get("handle", handle if isinstance(handle, str) else ""),
                start=p["started"],
                rank=rank,
                field_size=prep.field.size_rated or prep.field.size,
                points=points,
                penalty=penalty,
                performance=prep.performance(rank),
                old_rating=int(round(rating)),
                new_rating=int(round(new_rating)),
                delta=int(round(new_rating - rating)),
                confidence=prep.confidence(internal) if rated else "unrated",
                rated=rated,
                live=bool(p.get("live")),
                unsolved=[str(i) for i in prep.problem_index
                          if i in results and not results[i].solved],
                attempted=[str(i) for i in prep.problem_index
                           if i in results and not results[i].solved and results[i].rejects > 0],
            )
            if rated:
                rating = new_rating
                completed += 1
    finally:
        pool.shutdown(wait=False)


def build_career(handle: str, **kw) -> list[Entry]:
    return list(iter_career(handle, **kw))


def _scored_rounds(participations, prepare):
    """(prepared contest, rank) per round, computed once.

    Scoring re-parses a round's submissions, which is far too expensive to repeat inside the
    counterfactual loop: one chain pass over 134 rounds costs 1.2 s, so redoing it per round
    would be 155 s of blocking work. The rank never depends on the rating, so it is fixed.
    """
    out = []
    for p in participations:
        prep = prepare(p["contest_id"])
        if prep is None:
            continue
        if p.get("points") is not None:
            points, penalty = p["points"], p["penalty"]
        else:
            points, penalty, _ = contest_mod.score_submissions(prep, p["submissions"])
        out.append((p["contest_id"], prep, prep.rank_for(points, penalty)))
    return out


def _final_rating(scored, start_rating, skip_index=None) -> float:
    """The rating a chain of pre-scored rounds ends on. Arithmetic only."""
    rating = float(start_rating)
    completed = 0
    for i, (_, prep, rank) in enumerate(scored):
        if i == skip_index:
            continue
        internal = rating + cf.internal_offset(completed, prep.start)
        if not prep.is_rated_for(internal):
            continue
        rating += prep.delta_for(internal, rank) + cf.promotion(completed, prep.start)
        completed += 1
    return rating


def alternate_timelines(participations, prepare=contest_mod.prepare, start_rating=None):
    """Where you would stand today had you skipped each round in turn.

    galen_colin worked this out by hand for a single contest and made the point that carries
    the whole idea (codeforces.com/blog/entry/79415): a -166 disaster had shrunk to a 25 point
    difference six rounds later. A chained career can answer it for every round at once, which
    is the honest reply to "that one contest ruined my rating".

    Returns {contest_id: final rating without that round}, plus the real final rating.
    """
    if not participations:
        return {}, 0.0
    if start_rating is None:
        first = participations[0]["started"]
        start_rating = START_RATING if cf.uses_new_account_rule(first) else cf.LEGACY_START_RATING

    scored = _scored_rounds(participations, prepare)
    actual = _final_rating(scored, start_rating)
    out = {cid: _final_rating(scored, start_rating, skip_index=i)
           for i, (cid, _, _) in enumerate(scored)}
    return out, actual


def summarize(handles, entries: list[dict], real: list[dict], real_handle="") -> dict:
    rated = [e for e in entries if e["rated"]]
    virtual = rated[-1]["new_rating"] if rated else START_RATING
    if isinstance(handles, str):
        handles = [handles]
    return {
        "handle": " + ".join(handles),
        "handles": handles,
        "real_handle": real_handle or (handles[0] if handles else ""),
        "rating": virtual,
        "peak": max((e["new_rating"] for e in rated), default=START_RATING),
        "contests": len(rated),
        "real_rating": real[-1]["rating"] if real else None,
        "divergence": (virtual - real[-1]["rating"]) if real and rated else None,
    }


def career_json(handle, **kw) -> dict:
    handles = parse_handles(handle) if isinstance(handle, str) else list(handle)
    entries = [asdict(e) for e in build_career(handles, **kw)]
    primary = main_handle(handles)
    real = real_curve(primary)
    return {**summarize(handles, entries, real, primary), "entries": entries, "real": real}
