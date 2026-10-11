"""AtCoder rating math, checked against AtCoder's own published history."""
import json
import urllib.request

import pytest

from vrating.rating import ac


def history(user):
    req = urllib.request.Request(f"https://atcoder.jp/users/{user}/history/json",
                                 headers={"User-Agent": "Mozilla/5.0"})
    return [x for x in json.load(urllib.request.urlopen(req)) if x["IsRated"]]


@pytest.mark.gate
@pytest.mark.parametrize("user", ["tourist", "chokudai"])
def test_rating_matches_official(user):
    perfs, errs = [], []
    for row in history(user):
        perfs.append(row["Performance"])          # capped, not InnerPerformance
        errs.append(round(ac.rating(perfs)) - row["NewRating"])
    assert all(e == 0 for e in errs), f"{user}: {sum(e != 0 for e in errs)} of {len(errs)} wrong"


def test_correction_is_1200_at_one_contest():
    assert ac._correction(1) == pytest.approx(1200.0)
    assert ac._correction(200) == pytest.approx(0.0, abs=1e-6)


def test_single_contest_rating_is_performance_minus_1200():
    assert ac.rating([2455]) == pytest.approx(1255, abs=0.5)


def test_positivize_keeps_ratings_above_zero():
    assert 0 < ac.rating([100]) < 100


def test_aperf_is_log_space_not_linear():
    """Two performances 800 apart average above their arithmetic mean."""
    assert ac.aperf([1200, 2000]) > 1600


def test_performance_for_rank_interpolates():
    places, perfs = [1, 10, 100], [2400.0, 1800.0, 1000.0]
    assert ac.performance_for_rank(1, places, perfs) == 2400
    assert ac.performance_for_rank(10, places, perfs) == 1800
    assert 1000 < ac.performance_for_rank(55, places, perfs) < 1800
    assert ac.performance_for_rank(9999, places, perfs) == 1000
