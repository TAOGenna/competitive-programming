"""AtCoder data access.

What is public, and what is not:
  - results/json   every participant's Place and Performance. Public. This is the whole
                   rank -> performance curve, which is all the rating maths needs.
  - history/json   a user's own rated history. Public.
  - standings/json 302s to a login page. Scores and submission times are gated, which is
                   why a virtual rank has to be supplied rather than derived.
  - kenkoooo       AtCoder Problems' submission API is public and un-gated; used to find
                   which contests a user has actually sat.

data.ac-predictor.com mirrors results/json with CORS headers; atcoder.jp does not.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .cf import DATA

ATCODER = "https://atcoder.jp"
MIRROR = "https://data.ac-predictor.com"
KENKOOOO = "https://kenkoooo.com/atcoder"
UA = {"User-Agent": "vrating (personal virtual-rating tool)"}
MIN_INTERVAL = 1.0

_lock = threading.Lock()
_last = [0.0]


class AtCoderError(RuntimeError):
    pass


_SAFE_ID = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")


def safe_id(value: str) -> str:
    """Validate an identifier that is about to become both a URL path and a filename.

    Contest ids arrive from the query string. Without this, '../../x' escapes the cache
    directory on write and rewrites the outbound request path. Allow-list, not deny-list.
    """
    text = str(value)
    if not _SAFE_ID.match(text):
        raise AtCoderError(f"invalid contest id: {value!r}")
    return text


def _throttle():
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def _get(url):
    _throttle()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise AtCoderError(f"{url}: HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise AtCoderError(f"{url}: {exc.reason}") from None


def _cached(name, fetch):
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return json.loads(path.read_text())
    value = fetch()
    path.write_text(json.dumps(value))
    return value


def results(contest_id: str) -> list[dict]:
    """Every participant's Place, Performance, IsRated for a finished contest."""
    contest_id = safe_id(contest_id)

    def fetch():
        try:
            return _get(f"{MIRROR}/results/{contest_id}.json")
        except AtCoderError:
            return _get(f"{ATCODER}/contests/{contest_id}/results/json")
    return _cached(f"ac/results/{contest_id}.json", fetch)


def rank_curve(contest_id: str):
    """Ascending places with their performances -- the curve a virtual rank reads off.

    Only rated rows carry a performance, and unrated entrants are reported as 0.
    """
    rows = [r for r in results(contest_id) if r.get("IsRated")]
    rows.sort(key=lambda r: r["Place"])
    places = [int(r["Place"]) for r in rows]
    perfs = [float(r["Performance"]) for r in rows]
    return places, perfs


def user_history(user: str) -> list[dict]:
    """A user's rated contest history: Performance, NewRating, IsRated, per contest."""
    return _get(f"{ATCODER}/users/{urllib.parse.quote(user, safe='')}/history/json")


def user_submissions(user: str, from_second: int = 0) -> list[dict]:
    """All of a user's submissions, from AtCoder Problems. Paged at 500 by the API."""
    out, cursor = [], from_second
    while True:
        page = _get(f"{KENKOOOO}/atcoder-api/v3/user/submissions"
                    f"?user={urllib.parse.quote(user)}&from_second={cursor}")
        if not page:
            break
        out.extend(page)
        if len(page) < 500:
            break
        newest = max(s["epoch_second"] for s in page)
        if newest <= cursor:
            break
        cursor = newest + 1
    return out


def contests() -> list[dict]:
    """Contest metadata: id, start_epoch_second, duration_second, rate_change."""
    return _cached("ac/contests.json", lambda: _get(f"{KENKOOOO}/resources/contests.json"))


def problems() -> list[dict]:
    """Problem metadata, notably which contest each problem belongs to."""
    return _cached("ac/problems.json", lambda: _get(f"{KENKOOOO}/resources/problems.json"))


PENALTY_SECONDS = 5 * 60


def contest_submissions(contest_id: str, log=None) -> list[dict]:
    """Every submission made during a contest, from AtCoder Problems.

    AtCoder gates standings behind a login, but every submission is public, so the standings
    can be rebuilt. Paging is by timestamp at 1000 rows a page, which is ~70 requests for a
    busy ABC -- slow once, then cached.
    """
    contest_id = safe_id(contest_id)
    path = DATA / "ac" / "subs" / f"{contest_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return json.loads(path.read_text())

    meta = {c["id"]: c for c in contests()}.get(contest_id)
    if meta is None:
        raise AtCoderError(f"unknown contest {contest_id}")
    start = meta["start_epoch_second"]
    end = start + meta["duration_second"]

    out, cursor, seen = [], start, set()
    while cursor <= end:
        page = _get(f"{KENKOOOO}/atcoder-api/v3/from/{cursor}")
        if not page:
            break
        for s in page:
            if s.get("contest_id") == contest_id and start <= s["epoch_second"] <= end:
                key = (s["user_id"], s["problem_id"], s["epoch_second"], s.get("id"))
                if key not in seen:
                    seen.add(key)
                    out.append({k: s[k] for k in
                                ("user_id", "problem_id", "epoch_second", "result", "point")})
        newest = max(s["epoch_second"] for s in page)
        if newest <= cursor:
            break
        cursor = newest + 1
        if log:
            log(min(cursor - start, end - start), end - start)
    path.write_text(json.dumps(out))
    return out


def score_attempt(submissions, start: int):
    """AtCoder scoring: total points, and the time of the last accept plus 5 min per reject.

    Rejects only count on problems that were eventually solved, which is why the walk is per
    problem rather than a raw count.
    """
    per: dict[str, list] = {}
    for s in sorted(submissions, key=lambda x: x["epoch_second"]):
        cur = per.setdefault(s["problem_id"], [None, 0, 0.0])
        if cur[0] is not None:
            continue                                  # already solved
        if s["result"] == "AC":
            cur[0], cur[2] = s["epoch_second"] - start, float(s.get("point") or 0)
        else:
            cur[1] += 1
    solved = [v for v in per.values() if v[0] is not None]
    score = sum(v[2] for v in solved)
    elapsed = max((v[0] + PENALTY_SECONDS * v[1] for v in solved), default=0)
    return score, elapsed


def rebuilt_standings(contest_id: str, log=None):
    """(score, elapsed) per user, sorted -- the ladder a virtual result slots into."""
    contest_id = safe_id(contest_id)
    meta = {c["id"]: c for c in contests()}[contest_id]
    start = meta["start_epoch_second"]
    by_user: dict[str, list] = {}
    for s in contest_submissions(contest_id, log=log):
        by_user.setdefault(s["user_id"], []).append(s)
    table = [score_attempt(v, start) for v in by_user.values()]
    table.sort(key=lambda r: (-r[0], r[1]))
    return table


def place_for(table, score: float, elapsed: float) -> int:
    """Where a score slots into a rebuilt ladder, using AtCoder's own ordering."""
    better = sum(1 for sc, el in table if (sc > score) or (sc == score and el < elapsed))
    return better + 1
