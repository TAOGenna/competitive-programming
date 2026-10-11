"""Chaining semantics, with a stub contest so the test needs no network."""
from dataclasses import dataclass

from vrating.career import engine
from vrating.rating import cf

MODERN = cf.NEW_ACCOUNT_RULE_START + 86400
LEGACY = cf.NEW_ACCOUNT_RULE_START - 86400


@dataclass
class StubField:
    size: int = 1000
    size_rated: int = 1000


class StubContest:
    """Awards a fixed delta, and records the rating it was asked about."""

    def __init__(self, delta=50, start=MODERN, rated_band=(-500, 4000)):
        self.delta, self.start = delta, start
        self.band = rated_band
        self.seen = []
        self.field = StubField()
        self.name, self.type = "Stub Round", "CF"
        self.problem_index, self.problem_points, self.duration = [], [], 7200

    def rank_for(self, points, penalty):
        return 100

    def delta_for(self, rating, rank):
        self.seen.append(rating)
        return self.delta

    def performance(self, rank):
        return 1500

    def is_rated_for(self, rating):
        return self.band[0] <= rating <= self.band[1]

    def confidence(self, rating):
        return "exact"


def run(stubs, starts=None):
    starts = starts or [s.start for s in stubs]
    parts = [{"contest_id": i, "started": t, "submissions": []}
             for i, t in enumerate(starts)]
    lookup = dict(enumerate(stubs))
    return list(engine.iter_career("x", participations=parts, prepare=lookup.get))


def test_rating_chains_forward():
    """Each round starts from where the previous one left off, not from the real rating."""
    a, b, c = StubContest(delta=100), StubContest(delta=-30), StubContest(delta=10)
    out = run([a, b, c])
    assert [e.old_rating for e in out] == [0, 600, 920]
    assert [e.new_rating for e in out] == [600, 920, 1180]
    # 0 -> +100 delta +500 promotion = 600; -> -30 +350 = 920; -> +10 +250 = 1180


def test_unrated_round_does_not_advance_the_career():
    """A round you'd have been ineligible for leaves the rating and the promotion clock alone."""
    a = StubContest(delta=100)
    skipped = StubContest(delta=999, rated_band=(3000, 4000))
    b = StubContest(delta=100)
    out = run([a, skipped, b])
    assert out[1].rated is False and out[1].delta == 0
    assert out[1].confidence == "unrated"
    # b still receives the *second* promotion, not the third
    assert out[2].new_rating == out[2].old_rating + 100 + cf.PROMOTIONS[1]


def test_provisional_offset_is_applied_to_the_rating_the_contest_sees():
    """A displayed 0 must be presented to the calculator as the internal 1400."""
    a = StubContest(delta=0)
    run([a])
    assert a.seen == [1400.0]


def test_legacy_accounts_start_at_1500_with_no_promotions():
    a = StubContest(delta=25, start=LEGACY)
    out = run([a])
    assert out[0].old_rating == cf.LEGACY_START_RATING
    assert out[0].new_rating == cf.LEGACY_START_RATING + 25
    assert a.seen == [1500.0]


def test_summary_reports_divergence_from_real_rating():
    out = [e.__dict__ for e in run([StubContest(delta=100)])]
    s = engine.summarize("x", out, [{"t": 1, "rating": 500}])
    assert s["rating"] == 600 and s["real_rating"] == 500 and s["divergence"] == 100


def test_summary_without_real_history():
    out = [e.__dict__ for e in run([StubContest(delta=100)])]
    assert engine.summarize("x", out, [])["divergence"] is None


def test_same_contest_on_two_accounts_counts_once(monkeypatch):
    def fake(handle):
        t = {"alt": 100, "main": 500}[handle]
        return [{"contestId": 7, "author": {"participantType": "VIRTUAL", "startTimeSeconds": t}}]
    monkeypatch.setattr(engine.src, "user_submissions", fake)
    parts = engine.virtual_participations(["main", "alt"])
    assert len(parts) == 1
    assert parts[0]["handle"] == "alt" and parts[0]["started"] == 100


def test_parse_handles_accepts_commas_and_spaces_and_drops_repeats():
    assert engine.parse_handles("a, b  c") == ["a", "b", "c"]
    assert engine.parse_handles("Bob, bob, BOB") == ["Bob"]
    assert engine.parse_handles("  ") == []


def test_summary_names_every_account():
    out = [e.__dict__ for e in run([StubContest(delta=10)])]
    s = engine.summarize(["alt", "main"], out, [{"t": 1, "rating": 500}], real_handle="main")
    assert s["handles"] == ["alt", "main"]
    assert s["handle"] == "alt + main"
    assert s["real_handle"] == "main"


def test_rounds_are_prepared_in_parallel_without_losing_streaming(monkeypatch):
    """Preparation fans out, but the first result must still arrive as early as it would
    have sequentially -- an earlier attempt used `with ThreadPoolExecutor(...)`, whose exit
    waits for every future and silently turned the stream into a batch."""
    import time

    def slow_prepare(cid):
        time.sleep(0.2)
        return StubContest()

    parts = [{"contest_id": i, "started": MODERN + i, "submissions": []} for i in range(8)]
    started = time.monotonic()
    gen = engine.iter_career("x", participations=parts, prepare=slow_prepare)
    next(gen)
    first = time.monotonic() - started
    list(gen)
    total = time.monotonic() - started

    assert first < 0.5, f"first entry took {first:.2f}s; streaming regressed to batch"
    assert total < 1.2, f"all 8 took {total:.2f}s; expected well under the 1.6s serial cost"


def test_alternate_timelines_recomputes_the_chain_without_each_round():
    """galen_colin's argument, made mechanical: what would you be rated had you skipped a
    round? The chain has to be rerun, not just the delta subtracted, because every later
    round was scored against a rating that would have been different."""
    a, b, c = StubContest(delta=100), StubContest(delta=-30), StubContest(delta=10)
    parts = [{"contest_id": i, "started": MODERN + i, "submissions": []} for i in range(3)]
    lookup = {0: a, 1: b, 2: c}

    alts, actual = engine.alternate_timelines(parts, prepare=lookup.get)
    assert actual == 1180                       # 0 +100+500, -30+350, +10+250
    assert set(alts) == {0, 1, 2}

    # dropping the middle round also shifts which promotion the last one receives,
    # so the answer is not simply actual + 30
    assert alts[1] != actual + 30
    assert alts[1] == 960                       # 0 +100+500 = 600, then +10+350


def test_alternate_timelines_is_empty_for_no_rounds():
    assert engine.alternate_timelines([], prepare=lambda c: None) == ({}, 0.0)


def test_alternate_timelines_scores_each_round_once(monkeypatch):
    """The counterfactual loop is O(rounds^2) chain passes, so anything expensive inside it
    must be hoisted. Scoring re-parses submissions; leaving it in the loop cost 155 s on a
    134-round career instead of 1.8 s. Asserted by counting calls, not by timing."""
    calls = []
    real = engine.contest_mod.score_submissions
    monkeypatch.setattr(engine.contest_mod, "score_submissions",
                        lambda prep, subs: (calls.append(1), real(prep, subs))[1])

    stubs = [StubContest(delta=10) for _ in range(6)]
    parts = [{"contest_id": i, "started": MODERN + i, "submissions": []} for i in range(6)]
    engine.alternate_timelines(parts, prepare=dict(enumerate(stubs)).get)

    assert len(calls) == 6, f"scored {len(calls)} times for 6 rounds; should be once each"
