"""Reconstruct a Codeforces contest score from raw submissions.

Needed because contest.standings will not serve virtual rows, so a virtual participant's
points and penalty have to be derived from contest.status.

Both rules below were fitted against official standings and match exactly:
  CF-type   : max(0.3P, P - (P/250)*floor(t/60) - 50*wrong)   [62,192 cells, 100%]
  ICPC-type : points = solved count, penalty = sum(floor(t/60) + 10*wrong)  [100%]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

NON_PENALIZED = {"COMPILATION_ERROR", "TESTING", "OK"}
ICPC_PENALTY_PER_WRONG = 10


def _is_penalized(submission) -> bool:
    """Whether a failed submission counts as an unsuccessful attempt.

    Codeforces does not penalize a submission that fails on the samples, which show up as
    passedTestCount == 0. Everything that got past the samples counts, including SKIPPED
    (a superseded pretest-passing solution) and CHALLENGED. Verified cell-by-cell against
    the official rejectedAttemptCount.
    """
    verdict = submission.get("verdict")
    if verdict in NON_PENALIZED:
        return False
    return (submission.get("passedTestCount") or 0) > 0


@dataclass(frozen=True)
class ProblemResult:
    solved: bool
    time_seconds: int   # of the accepted submission; -1 if unsolved
    rejects: int        # penalized attempts before the accepted one


def problem_results(submissions, problem_indexes, duration_seconds) -> dict[str, ProblemResult]:
    """Collapse a participant's submissions into one result per problem.

    `submissions` need only carry problem index, verdict and relativeTimeSeconds.
    Submissions after the contest clock ran out are ignored.
    """
    # NOTE: participants whose every submission is SKIPPED (disqualified) are not modelled --
    # Codeforces zeroes some such rows and keeps the attempt counts on others, with no
    # observable discriminator. It cannot affect a virtual participant, whose own submissions
    # are judged normally, and it never changes points or penalty (those problems are unsolved).
    by_problem: dict[str, list] = {idx: [] for idx in problem_indexes}
    for s in submissions:
        idx = s["problem"]["index"]
        t = s.get("relativeTimeSeconds", 1 << 30)
        if idx not in by_problem or t >= duration_seconds:
            continue
        by_problem[idx].append((t, s))

    out = {}
    for idx, subs in by_problem.items():
        subs.sort(key=lambda x: x[0])
        rejects = 0
        result = ProblemResult(False, -1, 0)
        for t, s in subs:
            if s.get("verdict") == "OK":
                result = ProblemResult(True, t, rejects)
                break
            if _is_penalized(s):
                rejects += 1
        if not result.solved:
            result = ProblemResult(False, -1, rejects)
        out[idx] = result
    return out


def cf_problem_score(max_points: float, time_seconds: int, rejects: int, duration_minutes: int) -> float:
    """Points for one solved problem in a CF-type round.

    A problem sheds 48% of its value over the full round, so the per-minute decay is
    max_points / (duration * 25/12) -- 250 for the usual 120-minute round -- and the
    accumulated decay is floored. Verified to 100% on 7 rounds of 120/150/180 minutes.
    """
    minutes = math.floor(time_seconds / 60)
    decay = math.floor(max_points * minutes * 12.0 / (25.0 * duration_minutes))
    return max(0.3 * max_points, max_points - decay - 50 * rejects)


def score(results: dict[str, ProblemResult], problem_points, problem_indexes, contest_type: str,
          duration_seconds: int):
    """Total (points, penalty) for a participant, matching Codeforces' own ordering keys."""
    if contest_type == "ICPC":
        solved = sum(1 for r in results.values() if r.solved)
        penalty = sum(
            math.floor(r.time_seconds / 60) + ICPC_PENALTY_PER_WRONG * r.rejects
            for r in results.values()
            if r.solved
        )
        return float(solved), float(penalty)

    duration_minutes = duration_seconds // 60
    total = 0.0
    for idx, max_points in zip(problem_indexes, problem_points):
        r = results.get(idx)
        if r is not None and r.solved:
            total += cf_problem_score(max_points, r.time_seconds, r.rejects, duration_minutes)
    return float(total), 0.0
