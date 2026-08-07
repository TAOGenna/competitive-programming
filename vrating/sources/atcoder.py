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
