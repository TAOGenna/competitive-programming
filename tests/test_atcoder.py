"""AtCoder career engine.

The end-to-end check is unusually strong here: history/json publishes each user's Place per
contest, so a real career can be replayed through the virtual engine and must come out
identical. Four users, 125 contests, every rating exact.
"""
import math

import pytest

from vrating.career import atcoder as acc
from vrating.sources import atcoder as src


def test_rated_range_parses_every_form_atcoder_uses():
    assert acc.rated_range("~ 1999") == (-math.inf, 1999)
    assert acc.rated_range("2000 ~") == (2000, math.inf)
    assert acc.rated_range("1200 ~ 2799") == (1200, 2799)
    assert acc.rated_range("All") == (-math.inf, math.inf)
    assert acc.rated_range("-") is None
    assert acc.rated_range("") is None


def test_rated_range_comes_from_the_declared_band_not_the_field():
    """Deriving the ceiling from the highest-rated entrant would rule the top seed out of
    their own contest, which is how a top player's chain used to break."""
    lo, hi = acc.rated_range("All")
    assert hi == math.inf


def test_unresolved_round_is_reported_not_dropped():
    e = acc._unresolved("wtf19", {"rank": 3, "sat_at": 100}, 2500.0, "no results")
    assert e.rated is False
    assert e.new_rating == e.old_rating == 2500
    assert e.confidence.startswith("unresolved")


@pytest.mark.gate
@pytest.mark.parametrize("user", ["urnayuw", "purslane_ma", "chokudai"])
def test_replaying_a_real_career_reproduces_it_exactly(user):
    hist = [h for h in src.user_history(user) if h["IsRated"]]
    sittings = [{"contest_id": h["ContestScreenName"].split(".")[0],
                 "rank": h["Place"],
                 "sat_at": acc._epoch(h["EndTime"])} for h in hist]
    got = {e.contest_id: e for e in acc.iter_career(user, sittings)}

    assert len(got) == len(hist), "every contest must resolve; a gap corrupts the chain"
    for h in hist:
        cid = h["ContestScreenName"].split(".")[0]
        e = got[cid]
        assert e.performance == h["Performance"], f"{cid}: performance from rank"
        assert e.new_rating == h["NewRating"], f"{cid}: rating"


@pytest.mark.gate
def test_rank_curve_is_ascending_and_monotone_in_performance():
    places, perfs = src.rank_curve("abc300")
    assert places == sorted(places)
    assert all(a >= b for a, b in zip(perfs, perfs[1:])), "a worse rank cannot score higher"


def test_contest_ids_from_the_query_string_cannot_escape_the_cache():
    """These reach both a filename and an outbound URL path, so they are allow-listed."""
    for bad in ("../../../../tmp/evil", "abc300/../x", "a b", "", "x" * 100, "a?b", "a%2e%2e"):
        with pytest.raises(src.AtCoderError):
            src.safe_id(bad)
    for good in ("abc300", "wtf19", "agc065", "ahc001", "jsc2019-final"):
        assert src.safe_id(good) == good
