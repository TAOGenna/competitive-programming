"""Codeforces API access with an on-disk cache.

Two API constraints shape this module:
  - ~1 request/second, enforced globally by `_throttle`.
  - contest.standings rejects every extra parameter for non-admins, so it can only be
    fetched whole and anonymously. It is large (~7 MB), hence the compact .npz cache.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

API = "https://codeforces.com/api"
DATA = Path(os.environ.get("VRATING_DATA", Path(__file__).resolve().parents[2] / "data"))
MIN_INTERVAL = 1.05

_lock = threading.Lock()
_last = [0.0]


def _throttle():
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


class CodeforcesError(RuntimeError):
    """The API refused a request. Carries the API's own explanation where there is one."""


def _get(method: str, **params) -> object:
    # handles are user input and land in a query string; encode rather than interpolate
    q = urllib.parse.urlencode(params)
    url = f"{API}/{method}" + (f"?{q}" if q else "")
    _throttle()
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as exc:
        # Codeforces answers "no such thing" with 400 and a JSON body explaining why --
        # an unrated contest asked for its rating changes, for instance.
        try:
            comment = json.load(exc).get("comment", "")
        except Exception:
            comment = exc.reason
        raise CodeforcesError(f"{method}: {comment}") from None
    except urllib.error.URLError as exc:
        raise CodeforcesError(f"{method}: {exc.reason}") from None
    if payload.get("status") != "OK":
        raise CodeforcesError(f"{method}: {payload.get('comment')}")
    return payload["result"]


def _cached_json(name: str, fetch):
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return json.loads(path.read_text())
    value = fetch()
    path.write_text(json.dumps(value))
    return value


def contest_list() -> list[dict]:
    return _cached_json("contests.json", lambda: _get("contest.list"))


def problemset() -> list[dict]:
    """Every problem with its tags and difficulty rating. One request for all 11k."""
    return _cached_json("problemset.json",
                        lambda: _get("problemset.problems")["problems"])


def rating_changes(contest_id: int) -> dict | None:
    """Rated participants as columns: handles, rank, old, new. None if the contest was unrated.

    Stored columnar rather than as the API's row JSON, which repeats the contest name on
    every row -- that alone was ~2 MB per large contest.
    """
    path = DATA / "rc" / f"{contest_id}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = DATA / "rc" / f"{contest_id}.json"

    if path.exists():
        z = np.load(path, allow_pickle=False)
        if len(z["handles"]) == 0:
            return None
        return {"name": str(z["name"]), "handles": list(z["handles"]),
                "rank": z["rank"], "old": z["old"], "new": z["new"]}

    if legacy.exists():
        rows = json.loads(legacy.read_text())
    else:
        try:
            rows = _get("contest.ratingChanges", contestId=contest_id)
        except CodeforcesError:
            rows = []                      # unrated contest, or one the API will not serve

    out = {
        "name": rows[0]["contestName"] if rows else "",
        "handles": [r["handle"] for r in rows],
        "rank": np.array([r["rank"] for r in rows], np.int32),
        "old": np.array([r["oldRating"] for r in rows], np.int32),
        "new": np.array([r["newRating"] for r in rows], np.int32),
    }
    np.savez_compressed(path, name=out["name"], handles=np.array(out["handles"]),
                        rank=out["rank"], old=out["old"], new=out["new"])
    legacy.unlink(missing_ok=True)
    return out if rows else None


def standings(contest_id: int) -> dict:
    """Compact standings: handles, points, penalty, plus problem metadata.

    Cached as .npz because the raw JSON is ~7 MB and parsing it dominates load time.
    """
    path = DATA / "st" / f"{contest_id}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        z = np.load(path, allow_pickle=False)
        return {
            "handles": list(z["handles"]),
            "points": z["points"],
            "penalty": z["penalty"],
            "pr_points": z["pr_points"],
            "pr_time": z["pr_time"],
            "pr_rejects": z["pr_rejects"],
            "problem_points": z["problem_points"],
            "problem_index": list(z["problem_index"]),
            "duration": int(z["duration"]),
            "type": str(z["type"]),
            "start": int(z["start"]),
        }

    # A permanent refusal (gym, removed, still running) is cached as a tombstone. Without
    # this every request re-attempts the same doomed fetches at one per second, forever.
    dead = DATA / "st" / f"{contest_id}.dead"
    if dead.exists():
        raise CodeforcesError(f"contest.standings: {dead.read_text()[:120]}")
    try:
        res = _get("contest.standings", contestId=contest_id)
    except CodeforcesError as exc:
        dead.write_text(str(exc))
        raise
    nprob = len(res["problems"])
    handles, points, penalty = [], [], []
    pr_points, pr_time, pr_rejects = [], [], []
    for row in res["rows"]:
        party = row["party"]
        if party["participantType"] != "CONTESTANT" or len(party["members"]) != 1:
            continue
        handles.append(party["members"][0]["handle"])
        points.append(row["points"])
        penalty.append(row["penalty"])
        pp, pt, pj = [], [], []
        for r in row["problemResults"][:nprob]:
            pp.append(r.get("points", 0.0))
            pt.append(r.get("bestSubmissionTimeSeconds", -1))
            pj.append(r.get("rejectedAttemptCount", 0))
        pr_points.append(pp)
        pr_time.append(pt)
        pr_rejects.append(pj)
    problems = res["problems"]
    out = {
        "handles": handles,
        "points": np.array(points, float),
        "penalty": np.array(penalty, float),
        "pr_points": np.array(pr_points, float),
        "pr_time": np.array(pr_time, float),
        "pr_rejects": np.array(pr_rejects, float),
        "problem_points": np.array([p.get("points", 0) or 0 for p in problems], float),
        "problem_index": [p["index"] for p in problems],
        "duration": int(res["contest"]["durationSeconds"]),
        "type": res["contest"]["type"],
        "start": int(res["contest"].get("startTimeSeconds", 0)),
    }
    np.savez_compressed(
        path,
        handles=np.array(out["handles"]),
        points=out["points"],
        penalty=out["penalty"],
        pr_points=out["pr_points"],
        pr_time=out["pr_time"],
        pr_rejects=out["pr_rejects"],
        problem_points=out["problem_points"],
        problem_index=np.array(out["problem_index"]),
        duration=out["duration"],
        type=out["type"],
        start=out["start"],
    )
    return out


def contest_submissions(contest_id: int, handle: str) -> list[dict]:
    """Every submission `handle` made in `contest_id`, including virtual ones.

    contest.status does accept a handle, unlike contest.standings.
    """
    return _get("contest.status", contestId=contest_id, handle=handle)


def user_submissions(handle: str) -> list[dict]:
    return _get("user.status", handle=handle)


def user_rating(handle: str) -> list[dict]:
    return _get("user.rating", handle=handle)
