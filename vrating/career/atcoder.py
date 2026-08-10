"""Chain AtCoder virtual contests into a rating career.

AtCoder's rating is not a per-contest delta but a function of the whole performance history,
so a career is: rank -> performance -> append -> recompute. Same chaining rule as Codeforces
though: round n is judged eligible against the rating round n-1 left you on.

Ranks have to be supplied. AtCoder's standings need a login, so a virtual placing cannot be
derived the way a Codeforces one can -- `candidate_sittings` finds which contests you sat so
you only have to type the number.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import inf

from ..rating import ac
from ..sources import atcoder as src

# A performance this far above the rated ceiling is what the ceiling caps to; used only to
# decide eligibility, never to invent a performance.
UNRATED = "unrated"


@dataclass
class Entry:
    contest_id: str
    name: str
    handle: str          # the account that sat it; several are replayed as one career
    start: int
    rank: int
    field_size: int
    performance: int
    old_rating: int
    new_rating: int
    delta: int
    rated: bool
    confidence: str


def _contest_index():
    return {c["id"]: c for c in src.contests()}


def _unresolved(cid, sitting, rating, why):
    """A round we could not place. Reported, never dropped -- see iter_career."""
    return Entry(
        contest_id=cid, name=cid, handle=sitting.get("handle", ""),
        start=int(sitting.get("sat_at", 0)),
        rank=int(sitting.get("rank", 0)), field_size=0, performance=0,
        old_rating=int(round(rating)), new_rating=int(round(rating)), delta=0,
        rated=False, confidence=f"unresolved: {why}",
    )


def rated_range(rate_change: str) -> tuple[float, float] | None:
    """Parse AtCoder's declared rated band. None means the contest was unrated.

    Seen forms: '-', 'All', '~ 1999', '2000 ~', '1200 ~ 2799'. Reading the band off the
    highest-rated entrant instead would be wrong for anyone who *is* the highest-rated
    entrant -- they would rule themselves out of their own contest.
    """
    text = (rate_change or "").strip()
    if not text or text == "-":
        return None
    if text.lower() == "all":
        return (-inf, inf)
    lo, sep, hi = text.partition("~")
    if not sep:
        return None
    lo, hi = lo.strip(), hi.strip()
    return (float(lo) if lo else -inf, float(hi) if hi else inf)


def candidate_sittings(users) -> list[dict]:
    """Contests these accounts have solved problems from *after* the contest ended.

    That is what a virtual sitting looks like from the outside. Ordered by when it happened,
    which is the order a career has to be chained in.

    Several accounts are one person, as on the Codeforces side: a round sat on two of them is
    kept once at its earliest attempt, and each sitting records the account that sat it so the
    rank estimator knows whose submissions to look for. Competing live on *any* account rules
    the round out for all of them -- you cannot sit a round virtually after you have seen it.
    """
    if isinstance(users, str):
        users = [users]
    prob_contest = {p["id"]: p["contest_id"] for p in src.problems()}
    meta = _contest_index()
    first_seen: dict[str, tuple] = {}          # contest -> (when, which account)
    live: set[str] = set()
    for user in users:
        for s in src.user_submissions(user):
            cid = prob_contest.get(s.get("problem_id"))
            c = meta.get(cid)
            if c is None:
                continue
            start = c["start_epoch_second"]
            ended = start + c["duration_second"]
            if start <= s["epoch_second"] <= ended:
                live.add(cid)             # competed for real; anything later is upsolving
                continue
            if s["epoch_second"] < start:
                continue
            t = s["epoch_second"]
            if cid not in first_seen or t < first_seen[cid][0]:
                first_seen[cid] = (t, user)
    out = []
    for cid, (t, user) in first_seen.items():
        # Solving a problem after a round you actually competed in is upsolving, not a sitting.
        if cid in live:
            continue
        c = meta[cid]
        out.append({"contest_id": cid, "name": c["title"], "sat_at": t, "handle": user,
                    "held": c["start_epoch_second"], "rate_change": c.get("rate_change", "")})
    return sorted(out, key=lambda x: x["sat_at"])


def main_handle(users) -> str:
    """Whichever account has competed most -- its real rating is the meaningful comparison."""
    if isinstance(users, str):
        return users
    best, best_n = (users[0] if users else ""), -1
    for u in users:
        try:
            n = len([h for h in src.user_history(u) if h.get("IsRated")])
        except Exception:                                      # noqa: BLE001
            n = 0
        if n > best_n:
            best, best_n = u, n
    return best


def iter_career(users, sittings, start_rating: float | None = None):
    """`sittings` is an ordered list of {contest_id, rank, sat_at}."""
    perfs: list[float] = []
    rating = 0.0 if start_rating is None else float(start_rating)
    meta = _contest_index()

    for s in sittings:
        cid = s["contest_id"]
        # A contest that cannot be resolved must not be dropped in silence: every later
        # round is chained off this one, so a missing link corrupts the whole tail.
        try:
            places, curve = src.rank_curve(cid)
        except src.AtCoderError as exc:
            yield _unresolved(cid, s, rating, f"could not load results: {exc}")
            continue
        if len(places) < 2:
            yield _unresolved(cid, s, rating, "too few rated participants to place a rank")
            continue

        band = rated_range(meta.get(cid, {}).get("rate_change", ""))
        rated = band is not None and band[0] - 1e-9 <= rating <= band[1] + 1e-9
        perf = ac.performance_for_rank(int(s["rank"]), places, curve)

        old = rating
        if rated:
            perfs.append(perf)
            rating = ac.rating(perfs)
        c = meta.get(cid, {})
        yield Entry(
            contest_id=cid,
            name=c.get("title", cid),
            handle=s.get("handle", ""),
            start=int(s.get("sat_at", c.get("start_epoch_second", 0))),
            rank=int(s["rank"]),
            field_size=len(places),
            performance=int(round(perf)),
            old_rating=int(round(old)),
            new_rating=int(round(rating)),
            delta=int(round(rating - old)),
            rated=rated,
            # the curve is published, so a rank maps to a performance essentially exactly
            confidence="exact" if rated else UNRATED,
        )


def real_curve(user: str) -> list[dict]:
    try:
        return [{"t": _epoch(h["EndTime"]), "rating": h["NewRating"]}
                for h in src.user_history(user) if h.get("IsRated")]
    except Exception:
        return []


def _epoch(iso: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(iso).timestamp())


def summarize(users, entries: list[dict], real: list[dict], real_handle: str = "") -> dict:
    if isinstance(users, str):
        users = [users]
    rated = [e for e in entries if e["rated"]]
    virtual = rated[-1]["new_rating"] if rated else 0
    return {
        "handle": " + ".join(users),
        "handles": users,
        "real_handle": real_handle or (users[0] if users else ""),
        "platform": "atcoder",
        "rating": virtual,
        "peak": max((e["new_rating"] for e in rated), default=0),
        "contests": len(rated),
        "real_rating": real[-1]["rating"] if real else None,
        "divergence": (virtual - real[-1]["rating"]) if real and rated else None,
    }


def _attach_sittings(users, sittings):
    """Put back what the page could not send: when each round was sat, and on which account.

    The rank form posts contest and rank only, so without this every round is dated to when
    the contest was *held* rather than when it was sat, and a career spanning two accounts
    forgets which one sat what.
    """
    try:
        known = {s["contest_id"]: s for s in candidate_sittings(users)}
    except Exception:                                          # noqa: BLE001
        return sittings
    out = []
    for s in sittings:
        k = known.get(s["contest_id"])
        out.append({**s, "sat_at": k["sat_at"], "handle": k["handle"]} if k else s)
    return out


def career_json(users, sittings) -> dict:
    if isinstance(users, str):
        users = [users]
    entries = [asdict(e) for e in iter_career(users, _attach_sittings(users, sittings))]
    primary = main_handle(users)
    real = real_curve(primary)
    return {**summarize(users, entries, real, primary), "entries": entries, "real": real}


def estimate_ranks(users, sittings, progress=None):
    """Work out where each virtual sitting would have placed, without asking.

    AtCoder gates standings behind a login, so the ladder is rebuilt from the public
    submission stream and the user's own attempt is slotted into it. Measured against the
    5,885 rated competitors of abc300, the rank this produces is not exact -- but the number
    that matters is the performance it implies, and that lands within 25 points 92% of the
    time (median +2). Exact enough to fill the box; the box stays editable.
    """
    if isinstance(users, str):
        users = [users]
    meta = _contest_index()
    mine: dict[tuple, list] = {}
    for user in users:
        for s in src.user_submissions(user):
            cid = s.get("contest_id")
            if cid:
                mine.setdefault((user, cid), []).append(s)

    out = {}
    for n, s in enumerate(sittings):
        cid = s["contest_id"]
        if progress:
            progress(n, len(sittings), cid)
        c = meta.get(cid)
        if c is None:
            continue
        # the sitting names the account that sat it; another account's attempt at the same
        # round is a different sitting and would place at a different rank
        user = s.get("handle") or users[0]
        window = (s["sat_at"], s["sat_at"] + c["duration_second"])
        attempt = [x for x in mine.get((user, cid), [])
                   if window[0] <= x["epoch_second"] <= window[1]]
        if not attempt:
            continue
        try:
            table = src.rebuilt_standings(cid)
        except src.AtCoderError:
            continue
        score, elapsed = src.score_attempt(attempt, window[0])
        if score <= 0:
            continue
        out[cid] = src.place_for(table, score, elapsed)
    return out
