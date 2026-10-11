"""Golden tests: the calculator must reproduce Codeforces' own published deltas.

Div. 1 fields are the honest measure -- they are almost entirely established accounts,
so the provisional-rating distortion is negligible. Mixed-division fields are covered by
the calibration tests instead.
"""
import numpy as np
import pytest

from vrating.rating import cf
from vrating.sources import cf as src

DIV1 = [1852, 1889, 2196, 2249]


def load(contest_id):
    rc = src.rating_changes(contest_id)
    st = src.standings(contest_id)
    pts = dict(zip(st["handles"], st["points"]))
    pen = dict(zip(st["handles"], st["penalty"]))
    keep = np.array([h in pts for h in rc["handles"]])
    handles = [h for h, k in zip(rc["handles"], keep) if k]
    field = cf.build_field(rc["old"][keep], [pts[h] for h in handles], [pen[h] for h in handles])
    official = (rc["new"][keep] - rc["old"][keep]).astype(float)
    return field, official, handles


@pytest.mark.parametrize("contest_id", DIV1)
def test_div1_matches_official(contest_id):
    field, official, _ = load(contest_id)
    err = np.abs(cf.field_deltas(field) - official)
    within1 = float(np.mean(err <= 1))
    assert within1 >= 0.98, f"contest {contest_id}: only {within1:.1%} within +-1"


@pytest.mark.parametrize("contest_id", DIV1)
def test_single_query_matches_full_field(contest_id):
    """delta_for() must agree with the full-field computation for members of the field.

    This is what makes the O(log n) query path trustworthy: it is checked against the
    O(n log n) path that the golden test above validates against Codeforces itself.
    """
    field, _, _ = load(contest_id)
    full = cf.field_deltas(field)
    ranks = cf._reassign_ranks(field.points, field.penalty)
    adj = cf.adjustments(field, cf.raw_deltas(field, ranks))

    rng = np.random.default_rng(0)
    for i in rng.choice(field.size, size=60, replace=False):
        # self-exclusion differs by design: a field member is in the seed, an inserted
        # contestant is not. Rebuild the field without member i to compare like with like.
        keep = np.arange(field.size) != i
        sub = cf.build_field(field.ratings[keep], field.points[keep], field.penalty[keep])
        rank = sub.rank_of(float(field.points[i]), float(field.penalty[i]))
        got = cf.delta_for(sub, float(field.ratings[i]), rank, adj)
        assert abs(got - full[i]) <= 2, f"query {got} vs field {full[i]} at index {i}"


def test_tie_ranks_use_worst_rank():
    points = np.array([10.0, 10.0, 5.0])
    penalty = np.array([1.0, 1.0, 0.0])
    assert list(cf._reassign_ranks(points, penalty)) == [2, 2, 3]


def test_internal_offset_schedule():
    modern = cf.NEW_ACCOUNT_RULE_START + 1
    assert cf.internal_offset(0, modern) == 1400
    assert cf.internal_offset(1, modern) == 900
    assert cf.internal_offset(5, modern) == 50
    assert cf.internal_offset(6, modern) == 0
    assert cf.internal_offset(99, modern) == 0


def test_legacy_accounts_have_no_hidden_rating():
    """Before round 1360 a new account started at 1500 and showed its real rating."""
    legacy = cf.NEW_ACCOUNT_RULE_START - 1
    assert cf.internal_offset(0, legacy) == 0
    assert cf.promotion(0, legacy) == 0
    assert cf.promotion(0, cf.NEW_ACCOUNT_RULE_START + 1) == 500
