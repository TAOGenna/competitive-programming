"""The reconstruction gate.

Virtual rows are not available from contest.standings, so a virtual participant's score has
to be rebuilt from raw submissions. If that rebuild is wrong, every rating downstream is
fiction -- so it is checked against Codeforces' own standings for real contestants.

(points, penalty) is the assertion that matters: those two numbers are what rank you.
Per-problem cells are checked too, as a tighter net.

Network-bound at ~1 req/s. Run with: pytest -m gate
"""
import random

import pytest

from vrating.rating import scoring
from vrating.sources import cf as src

CONTESTS = [
    (1900, 25),   # CF-type, 120 min
    (2249, 20),   # CF-type, 150 min
    (2196, 20),   # CF-type, 180 min
    (2043, 25),   # ICPC-type (Educational)
]


def _reconstruct(contest_id, index):
    st = src.standings(contest_id)
    handle = st["handles"][index]
    subs = [s for s in src.contest_submissions(contest_id, handle)
            if s["author"]["participantType"] == "CONTESTANT"]
    # Disqualified participants (every submission SKIPPED) are a documented non-goal.
    if subs and all(s.get("verdict") == "SKIPPED" for s in subs):
        return None
    res = scoring.problem_results(subs, st["problem_index"], st["duration"])
    pts, pen = scoring.score(res, st["problem_points"], st["problem_index"],
                            st["type"], st["duration"])
    return st, handle, res, pts, pen


@pytest.mark.gate
@pytest.mark.parametrize("contest_id,n", CONTESTS)
def test_score_reconstruction_matches_official(contest_id, n):
    st = src.standings(contest_id)
    random.seed(11)
    picks = random.sample(range(len(st["handles"])), n)

    checked = 0
    for i in picks:
        got = _reconstruct(contest_id, i)
        if got is None:
            continue
        st, handle, res, pts, pen = got
        checked += 1
        assert pts == pytest.approx(st["points"][i]), f"{handle}: points"
        assert pen == pytest.approx(st["penalty"][i]), f"{handle}: penalty"
        for k, idx in enumerate(st["problem_index"]):
            r = res[idx]
            assert (r.time_seconds if r.solved else -1) == st["pr_time"][i][k], f"{handle} {idx}: time"
            assert r.rejects == st["pr_rejects"][i][k], f"{handle} {idx}: rejects"
    assert checked >= n - 2, "too many participants skipped to be a meaningful check"


def test_cf_decay_is_duration_relative():
    """A problem sheds 48% of its value over the round, whatever the round's length."""
    assert scoring.cf_problem_score(500, 0, 0, 120) == 500
    assert scoring.cf_problem_score(500, 120 * 60, 0, 120) == 260   # 500 - 240
    assert scoring.cf_problem_score(500, 150 * 60, 0, 150) == 260   # same fraction, longer round
    assert scoring.cf_problem_score(500, 60 * 60, 1, 120) == 330    # 500 - 120 decay - 50 penalty


def test_floor_at_30_percent():
    assert scoring.cf_problem_score(1000, 119 * 60, 10, 120) == 300


def test_sample_test_failures_are_not_penalized():
    subs = [
        {"problem": {"index": "A"}, "relativeTimeSeconds": 60, "verdict": "WRONG_ANSWER", "passedTestCount": 0},
        {"problem": {"index": "A"}, "relativeTimeSeconds": 120, "verdict": "WRONG_ANSWER", "passedTestCount": 3},
        {"problem": {"index": "A"}, "relativeTimeSeconds": 180, "verdict": "OK", "passedTestCount": 9},
    ]
    r = scoring.problem_results(subs, ["A"], 7200)["A"]
    assert (r.solved, r.time_seconds, r.rejects) == (True, 180, 1)


def test_submissions_after_the_clock_are_ignored():
    subs = [{"problem": {"index": "A"}, "relativeTimeSeconds": 7200, "verdict": "OK", "passedTestCount": 9}]
    assert scoring.problem_results(subs, ["A"], 7200)["A"].solved is False
