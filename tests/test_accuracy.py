"""Accuracy regression: predicted deltas vs the deltas Codeforces actually awarded.

Measured against established accounts (>=6 prior rated contests), which is the population any
real user of this tool belongs to. Provisional accounts are excluded because their *official*
delta includes a promotion that the career engine adds separately -- comparing against them
here would measure the wrong thing.

Thresholds sit a little above the observed numbers so an ordinary drift does not fail the
build, but a regression in the rating maths or the archive does.
"""
import numpy as np
import pytest

from vrating.career import contest as cm
from vrating.sources import archive
from vrating.sources import cf as src

# contest, rating band, max allowed median error, max allowed p90
CASES = [
    (1900, 1200, 1600, 2.0, 5.0),
    (1900, 1600, 2000, 2.0, 5.0),
    (2040, 1200, 1600, 2.0, 5.0),
    (1971, 1200, 1600, 2.0, 7.0),   # Div. 4: standings serve only half the rated field
    (2003,  800, 1600, 2.0, 5.0),   # ~73% served
    (1889, 1600, 4000, 1.0, 2.0),   # Div. 1: almost no provisional accounts in the field
]


def errors(contest_id, lo, hi, sample=400):
    prep = cm.prepare(contest_id)
    changes = src.rating_changes(contest_id)
    st = src.standings(contest_id)
    points = dict(zip(st["handles"], st["points"]))
    penalty = dict(zip(st["handles"], st["penalty"]))

    keep = np.array([h in points for h in changes["handles"]])
    handles = [h for h, k in zip(changes["handles"], keep) if k]
    displayed = changes["old"][keep].astype(float)
    official = (changes["new"][keep] - changes["old"][keep]).astype(float)

    prior = archive.prior_counts(contest_id)
    if prior is None:
        pytest.skip("archive not built")
    prior = prior[keep]

    idx = np.where((prior >= 6) & (displayed >= lo) & (displayed < hi))[0]
    if len(idx) < 30:
        pytest.skip("too few established accounts in band")
    rng = np.random.default_rng(1)
    idx = rng.choice(idx, size=min(sample, len(idx)), replace=False)

    pred = np.array([prep.delta_for(displayed[i],
                                    prep.rank_for(points[handles[i]], penalty[handles[i]]))
                     for i in idx])
    return np.abs(pred - official[idx])


@pytest.mark.gate
@pytest.mark.parametrize("contest_id,lo,hi,max_median,max_p90", CASES)
def test_delta_error_within_budget(contest_id, lo, hi, max_median, max_p90):
    err = errors(contest_id, lo, hi)
    median, p90 = float(np.median(err)), float(np.percentile(err, 90))
    assert median <= max_median, f"median {median} over budget {max_median}"
    assert p90 <= max_p90, f"p90 {p90} over budget {max_p90}"


@pytest.mark.gate
@pytest.mark.parametrize("contest_id", [2003, 1971])
def test_partially_served_standings_still_rank_correctly(contest_id):
    """Some rounds rate far more people than their standings expose -- 1971 rated 23,309 and
    serves 12,040, missing even the winner. Ranking against the visible subset would flatter
    a result roughly twofold, so ranks are mapped back onto the official scale. This asserts
    the recovered rank tracks the rank Codeforces actually awarded."""
    prep = cm.prepare(contest_id)
    assert prep.matched < 0.98
    assert prep.official_rank is not None
    assert prep.field.size_rated > prep.field.size

    changes = src.rating_changes(contest_id)
    st = src.standings(contest_id)
    points = dict(zip(st["handles"], st["points"]))
    penalty = dict(zip(st["handles"], st["penalty"]))
    keep = np.array([h in points for h in changes["handles"]])
    handles = [h for h, k in zip(changes["handles"], keep) if k]
    official = changes["rank"][keep]

    rng = np.random.default_rng(2)
    idx = rng.choice(len(handles), size=300, replace=False)
    recovered = np.array([prep.rank_for(points[handles[i]], penalty[handles[i]]) for i in idx])
    rel = np.abs(recovered - official[idx]) / np.maximum(official[idx], 1)
    assert np.median(rel) < 0.02, f"median rank error {np.median(rel):.1%}"


@pytest.mark.gate
def test_archive_raises_confidence_on_a_clean_field():
    prep = cm.prepare(1900)
    assert prep.matched == pytest.approx(1.0)
    assert prep.exact_field is True
    assert prep.confidence(1700) == "exact"
