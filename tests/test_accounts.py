"""Several accounts are one person.

Every rule here exists because a career that double-counts a round, or reads one account's
unsolved list against another's rating, is silently wrong rather than visibly broken.
"""
import urllib.error

import pytest

from vrating import config
from vrating.career import atcoder as acc, engine, upsolve
from vrating.sources import cf as src


# ---------- transient vs permanent ----------

def _http(code, comment):
    import io, json as _json
    body = io.BytesIO(_json.dumps({"status": "FAILED", "comment": comment}).encode())
    return urllib.error.HTTPError("u", code, comment, {}, body)


def _no_sleep(monkeypatch):
    monkeypatch.setattr(src.time, "sleep", lambda s: None)
    monkeypatch.setattr(src, "_throttle", lambda: None)


def test_a_503_is_retried_not_reported_as_a_missing_account(monkeypatch):
    """Codeforces sheds load with a 5xx when requests arrive together. Six accounts is twelve
    requests, and some come back 503 -- which used to be read as 'this account is gone'."""
    _no_sleep(monkeypatch)
    calls = []

    def flaky(url, timeout=None):
        calls.append(url)
        if len(calls) < 3:
            raise _http(503, "Service Unavailable")
        import io, json as _json
        return io.BytesIO(_json.dumps({"status": "OK", "result": [1, 2]}).encode())
    monkeypatch.setattr(src.urllib.request, "urlopen", flaky)
    assert src._get("user.status", handle="x") == [1, 2]
    assert len(calls) == 3


def test_a_deleted_account_is_permanent_and_not_retried(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def missing(url, timeout=None):
        calls.append(url)
        raise _http(400, "handle: User with handle ghost not found")
    monkeypatch.setattr(src.urllib.request, "urlopen", missing)
    with pytest.raises(src.MissingUser):
        src._get("user.status", handle="ghost")
    assert len(calls) == 1, "a missing account will not appear on a retry"


def test_a_persistent_outage_raises_rather_than_returning_nothing(monkeypatch):
    _no_sleep(monkeypatch)

    def down(url, timeout=None):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(src.urllib.request, "urlopen", down)
    with pytest.raises(src.Unavailable):
        src._get("user.status", handle="x")


def test_an_outage_is_never_written_to_the_cache_as_a_verdict(monkeypatch, tmp_path):
    """The cache records 'unrated' and 'will not serve this' as permanent facts. A contest
    tombstoned because Codeforces was briefly down stays wrong until the cache is deleted."""
    _no_sleep(monkeypatch)
    monkeypatch.setattr(src, "DATA", tmp_path)

    def down(url, timeout=None):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(src.urllib.request, "urlopen", down)

    with pytest.raises(src.Unavailable):
        src.rating_changes(9999)
    with pytest.raises(src.Unavailable):
        src.standings(9999)
    assert not list(tmp_path.rglob("9999.*")), "nothing may be recorded from an outage"


def test_an_unrated_contest_is_still_cached_as_unrated(monkeypatch, tmp_path):
    """The tombstone is load-bearing: without it every request re-attempts the same doomed
    fetch at one per second, forever."""
    _no_sleep(monkeypatch)
    monkeypatch.setattr(src, "DATA", tmp_path)

    def unrated(url, timeout=None):
        raise _http(400, "contestId: Rating changes are unavailable for this contest")
    monkeypatch.setattr(src.urllib.request, "urlopen", unrated)

    assert src.rating_changes(9999) is None
    assert (tmp_path / "rc" / "9999.npz").exists()


def test_a_genuine_bad_request_is_not_retried(monkeypatch):
    """An unrated contest asked for its rating changes answers 400 with an explanation, and
    will answer the same way forever."""
    _no_sleep(monkeypatch)
    calls = []

    def bad(url, timeout=None):
        calls.append(url)
        raise _http(400, "contestId: Contest with id 1 has not started")
    monkeypatch.setattr(src.urllib.request, "urlopen", bad)
    with pytest.raises(src.CodeforcesError):
        src._get("contest.ratingChanges", contestId=1)
    assert len(calls) == 1


# ---------- .env ----------

def test_env_file_is_read_but_never_beats_the_real_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# a comment\n\nVRATING_HANDLES=a, b\nexport VRATING_AC_HANDLES='c d'\n")
    monkeypatch.delenv("VRATING_HANDLES", raising=False)
    monkeypatch.setenv("VRATING_AC_HANDLES", "already_set")

    config.load_env(env)
    assert config.handles() == ["a", "b"]
    assert config.ac_handles() == ["already_set"]


def test_env_ignores_blank_and_malformed_lines(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("no_equals_sign\n=novalue\n   \nVRATING_HANDLES=\"x y\"\n")
    monkeypatch.delenv("VRATING_HANDLES", raising=False)
    assert config.load_env(env) == {"VRATING_HANDLES": "x y"}
    assert config.handles() == ["x", "y"]


def test_missing_env_file_is_not_an_error(tmp_path):
    assert config.load_env(tmp_path / "nope") == {}


# ---------- renamed accounts ----------

def test_a_renamed_handle_and_its_new_name_are_one_account(monkeypatch):
    """Codeforces answers to an old handle forever. Deduping the typed strings cannot see
    that two of them are the same person; only the API can."""
    monkeypatch.setattr(engine.src, "user_info",
                        lambda hs: [{"handle": "_Lunatic_" if h in ("Revenant86", "_Lunatic_")
                                     else h} for h in hs])
    assert engine.canonical_handles(["Revenant86", "what_is_spin", "_Lunatic_"]) \
        == ["_Lunatic_", "what_is_spin"]


def test_an_unknown_handle_is_dropped_without_taking_the_batch_with_it(monkeypatch):
    """user.info fails the whole request over one bad name, so the fallback asks one at a
    time -- otherwise a single deleted alt would blank out the entire list."""
    def fake(hs):
        if len(hs) > 1:
            raise engine.src.MissingUser("user.info: handles: no such user")
        if hs[0] == "gone":
            raise engine.src.MissingUser("no such user")
        return [{"handle": hs[0]}]
    monkeypatch.setattr(engine.src, "user_info", fake)
    assert engine.canonical_handles(["good", "gone", "other"]) == ["good", "other"]


def test_a_handle_that_merely_failed_to_resolve_is_kept(monkeypatch):
    """A 503 is not a deleted account. Dropping it here would remove the account from the
    career and report the shortened result as complete."""
    def fake(hs):
        if len(hs) > 1:
            raise engine.src.MissingUser("no such user")
        if hs[0] == "flaky":
            raise engine.src.CodeforcesError("user.info: Service Unavailable")
        return [{"handle": hs[0]}]
    monkeypatch.setattr(engine.src, "user_info", fake)
    assert engine.canonical_handles(["good", "flaky"]) == ["good", "flaky"]


def test_canonical_handles_falls_back_to_what_was_typed_when_offline(monkeypatch):
    def boom(hs):
        raise OSError("no network")
    monkeypatch.setattr(engine.src, "user_info", boom)
    assert engine.canonical_handles(["a", "b"]) == ["a", "b"]


def test_an_outage_does_not_report_that_every_account_is_gone(monkeypatch):
    """Codeforces wraps a network failure in the same error as 'no such user'. Resolving
    nothing means the API is down far more often than it means every account was deleted,
    and answering with an empty list would quietly replay nobody."""
    def down(hs):
        raise engine.src.CodeforcesError("user.info: <urlopen error timed out>")
    monkeypatch.setattr(engine.src, "user_info", down)
    assert engine.canonical_handles(["a", "b"]) == ["a", "b"]


# ---------- a stale alt must not take the rest down ----------

def test_one_dead_account_does_not_fail_the_whole_career(monkeypatch):
    """user.status does not answer to a renamed handle even though user.info does, so a list
    of alts collected over years will contain names that no longer resolve. One of them used
    to fail the entire replay."""
    def fake(handle):
        if handle == "gone":
            raise engine.src.MissingUser("user.status: User with handle gone not found")
        return [_virtual(7, 100)]
    monkeypatch.setattr(engine.src, "user_submissions", fake)
    parts = engine.virtual_participations(["gone", "alive"])
    assert [p["handle"] for p in parts] == ["alive"]


def test_a_transient_failure_never_silently_shortens_the_career(monkeypatch):
    """The bug this exists to stop: Codeforces answers a burst of requests with 503s, and
    treating that like a deleted account replayed 4 rounds of a 65-round career and presented
    the number as final. Only a missing account may be skipped; everything else must raise."""
    def fake(handle):
        if handle == "flaky":
            raise engine.src.CodeforcesError("user.status: Service Unavailable")
        return [_virtual(7, 100)]
    monkeypatch.setattr(engine.src, "user_submissions", fake)
    with pytest.raises(engine.src.CodeforcesError):
        engine.virtual_participations(["alive", "flaky"])


def test_upsolve_skips_a_dead_account_too(monkeypatch):
    def fake(handle):
        if handle == "gone":
            raise upsolve.src.MissingUser("not found")
        return [_virtual(7, 100, "A", "OK")]
    monkeypatch.setattr(upsolve.src, "user_submissions", fake)
    monkeypatch.setattr(upsolve.src, "user_rating", lambda h: [])
    monkeypatch.setattr(upsolve.src, "rating_changes", lambda cid: {"name": "R"})
    monkeypatch.setattr(upsolve.src, "standings", lambda cid: {
        "problem_index": ["A"], "duration": 7200, "handles": []})
    rounds, solved = upsolve.history(["gone", "alive"])
    assert [r["contest_id"] for r in rounds] == [7]
    assert (7, "A") in solved


# ---------- one round, one entry ----------

def _rating_row(cid, when):
    return {"contestId": cid, "ratingUpdateTimeSeconds": when, "oldRating": 1500,
            "newRating": 1510}


def test_a_round_both_accounts_competed_in_is_chained_once(monkeypatch):
    """Two entries would pay the round's delta twice on a timeline meant to be one person's."""
    monkeypatch.setattr(engine.src, "user_rating",
                        lambda h: [_rating_row(7, {"main": 500, "alt": 100}[h])])
    monkeypatch.setattr(engine.src, "standings", lambda cid: {
        "handles": ["main", "alt"], "points": [3.0, 4.0], "penalty": [10.0, 20.0]})

    parts = engine.real_participations(["main", "alt"])
    assert len(parts) == 1
    # the earliest sitting wins, exactly as group_virtual does for virtual ones
    assert parts[0]["handle"] == "alt" and parts[0]["started"] == 100
    assert parts[0]["points"] == 4.0


def test_merged_timeline_does_not_repeat_a_round_across_accounts(monkeypatch):
    monkeypatch.setattr(engine.src, "user_submissions", lambda h: [])
    monkeypatch.setattr(engine.src, "user_rating",
                        lambda h: [_rating_row(7, {"main": 500, "alt": 100}[h])])
    monkeypatch.setattr(engine.src, "standings", lambda cid: {
        "handles": ["main", "alt"], "points": [3.0, 4.0], "penalty": [10.0, 20.0]})
    assert [p["contest_id"] for p in engine.merged_participations(["main", "alt"])] == [7]


# ---------- upsolve agrees with the career ----------

def _virtual(cid, started, index="A", verdict="OK", passed=5):
    # passed > 0: got past the samples, so a failure here is a penalized attempt
    return {"contestId": cid, "problem": {"index": index}, "verdict": verdict,
            "passedTestCount": passed, "relativeTimeSeconds": 60,
            "author": {"participantType": "VIRTUAL", "startTimeSeconds": started}}


def test_upsolve_reads_the_same_sitting_the_career_scored(monkeypatch):
    """The career takes the earliest sitting of a round; the upsolve scan used to take
    whichever account was listed first. When they disagreed, the round's unsolved list
    described a sitting the career had never scored."""
    subs = {"main": [_virtual(7, 500, "A", "OK")],          # solved it on the later sitting
            "alt": [_virtual(7, 100, "A", "WRONG_ANSWER")]}  # the sitting that actually counts
    monkeypatch.setattr(upsolve.src, "user_submissions", lambda h: subs[h])
    monkeypatch.setattr(upsolve.src, "user_rating", lambda h: [])
    monkeypatch.setattr(upsolve.src, "rating_changes", lambda cid: {"name": "R"})
    monkeypatch.setattr(upsolve.src, "standings", lambda cid: {
        "problem_index": ["A"], "duration": 7200, "handles": []})

    rounds, solved = upsolve.history(["main", "alt"])
    assert [r["contest_id"] for r in rounds] == [7]
    assert rounds[0]["unsolved"] == ["A"]        # the alt's sitting: attempted, not solved
    assert rounds[0]["attempted"] == ["A"]
    # ...but having since solved it on any account still keeps it off the list
    assert (7, "A") in solved


def test_upsolve_pools_solved_problems_across_accounts(monkeypatch):
    prefetched = {
        "main": {"virtual": [], "solved": [[7, "A"]], "real": [], "ratings": {}},
        "alt": {"virtual": [], "solved": [[9, "B"]], "real": [], "ratings": {}},
    }
    _, solved = upsolve.history(["main", "alt"], prefetched=prefetched)
    assert solved == {(7, "A"), (9, "B")}


def test_upsolve_reads_a_real_round_against_that_account_s_own_rating(monkeypatch):
    """rating_then must come from the account that sat the round. Keyed only by contest, the
    last account read would overwrite it and the peer comparison would be made at a rating
    that account never held."""
    prefetched = {
        "main": {"virtual": [], "solved": [], "real": [7], "ratings": {"7": 1500}},
        "alt": {"virtual": [], "solved": [], "real": [], "ratings": {"7": 900}},
    }
    monkeypatch.setattr(upsolve.src, "rating_changes", lambda cid: {"name": "R"})
    monkeypatch.setattr(upsolve.src, "standings", lambda cid: {
        "handles": ["main"], "problem_index": ["A"], "duration": 7200,
        "pr_time": [[-1]], "pr_rejects": [[2]]})

    rounds, _ = upsolve.history(["main", "alt"], prefetched=prefetched)
    assert [r["rating_then"] for r in rounds] == [1500]


# ---------- AtCoder ----------

def _ac_sub(problem, when):
    return {"problem_id": problem, "epoch_second": when}


def _ac_world(monkeypatch, subs_by_user):
    contest = {"id": "abc300", "title": "ABC 300", "start_epoch_second": 1000,
               "duration_second": 100, "rate_change": "~ 1999"}
    monkeypatch.setattr(acc.src, "contests", lambda: [contest])
    monkeypatch.setattr(acc.src, "problems", lambda: [{"id": "abc300_a", "contest_id": "abc300"}])
    monkeypatch.setattr(acc.src, "user_submissions", lambda u: subs_by_user.get(u, []))


def test_atcoder_keeps_one_sitting_per_round_and_names_the_account(monkeypatch):
    _ac_world(monkeypatch, {"main": [_ac_sub("abc300_a", 9000)],
                            "alt": [_ac_sub("abc300_a", 5000)]})
    got = acc.candidate_sittings(["main", "alt"])
    assert [(s["contest_id"], s["sat_at"], s["handle"]) for s in got] == [("abc300", 5000, "alt")]


def test_atcoder_competing_live_on_any_account_rules_the_round_out(monkeypatch):
    """You cannot sit a round virtually after you have seen it, whichever login saw it."""
    _ac_world(monkeypatch, {"main": [_ac_sub("abc300_a", 1050)],    # live
                            "alt": [_ac_sub("abc300_a", 9000)]})    # "virtual", but too late
    assert acc.candidate_sittings(["main", "alt"]) == []


def test_atcoder_rank_estimate_looks_at_the_account_that_sat_it(monkeypatch):
    """Scoring the wrong account's submissions against a rebuilt ladder invents a rank."""
    _ac_world(monkeypatch, {"main": [], "alt": []})
    monkeypatch.setattr(acc.src, "user_submissions", lambda u: {
        "main": [{"contest_id": "abc300", "epoch_second": 6000}],
        "alt": [{"contest_id": "abc300", "epoch_second": 5050}],
    }[u])
    monkeypatch.setattr(acc.src, "rebuilt_standings", lambda cid: "TABLE")
    monkeypatch.setattr(acc.src, "score_attempt", lambda attempt, t0: (100, attempt[0]["epoch_second"] - t0))
    monkeypatch.setattr(acc.src, "place_for", lambda table, score, elapsed: elapsed)

    sittings = [{"contest_id": "abc300", "sat_at": 5000, "handle": "alt"}]
    assert acc.estimate_ranks(["main", "alt"], sittings) == {"abc300": 50}


def test_atcoder_summary_names_every_account():
    entries = [{"rated": True, "new_rating": 1200}]
    s = acc.summarize(["alt", "main"], entries, [{"t": 1, "rating": 1000}], real_handle="main")
    assert s["handle"] == "alt + main"
    assert s["handles"] == ["alt", "main"]
    assert s["real_handle"] == "main"
    assert s["divergence"] == 200
