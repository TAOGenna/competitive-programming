"""The upsolve recommender: isotonic solve curves and what they imply."""
import numpy as np
import pytest

from vrating.career import upsolve


def test_isotonic_leaves_a_monotone_sequence_alone():
    y = [0.1, 0.3, 0.5, 0.9]
    assert list(upsolve._isotonic(y, [1] * 4)) == pytest.approx(y)


def test_isotonic_pools_violations_into_their_weighted_mean():
    # 0.8 then 0.4 is impossible for a solve curve; they pool to the weighted mean
    out = upsolve._isotonic([0.2, 0.8, 0.4, 0.9], [1, 1, 1, 1])
    assert list(out) == pytest.approx([0.2, 0.6, 0.6, 0.9])
    assert all(a <= b + 1e-12 for a, b in zip(out, out[1:]))


def test_isotonic_respects_bin_population():
    """A 1000-person bin should pull a 10-person outlier, not the other way round."""
    out = upsolve._isotonic([0.9, 0.1], [1000, 10])
    assert out[0] == pytest.approx(out[1])
    assert out[0] > 0.85


def test_isotonic_output_is_always_non_decreasing():
    rng = np.random.default_rng(0)
    for _ in range(50):
        y = rng.random(12)
        w = rng.integers(1, 500, 12)
        out = upsolve._isotonic(y, w)
        assert all(a <= b + 1e-12 for a, b in zip(out, out[1:]))
        # pooling preserves the weighted total
        assert float(np.dot(out, w)) == pytest.approx(float(np.dot(y, w)))


def test_by_tag_ranks_by_how_often_a_tag_is_missed():
    mk = lambda tags, rate: upsolve.Suggestion(
        contest_id=1, index="A", name="n", contest_name="c", when=0,
        solve_rate=rate, peers=100, rating_then=1500, difficulty=1200, tags=tags,
        attempted=False)
    rows = upsolve.by_tag([mk(["dp", "math"], 0.9), mk(["dp"], 0.7), mk(["math"], 0.6)])
    assert rows[0]["tag"] == "dp" and rows[0]["count"] == 2
    assert rows[0]["mean_rate"] == pytest.approx(0.8)


@pytest.mark.gate
def test_solve_curve_is_monotone_and_ordered_by_problem_difficulty():
    """Later problems in a round are harder, so their curves must sit below the earlier ones."""
    from vrating.sources import cf as src
    centres, rates, counts = upsolve.solve_curves(1900)
    assert len(centres) >= 5 and counts.min() >= upsolve.MIN_PER_BIN
    for j in range(rates.shape[1]):
        col = rates[:, j]
        assert all(a <= b + 1e-12 for a, b in zip(col, col[1:])), f"problem {j} not monotone"
    # A of a Div. 2 round is solved far more often than its last problem
    assert rates[:, 0].mean() > rates[:, -1].mean() + 0.3


@pytest.mark.gate
def test_curve_reads_high_for_strong_ratings_and_low_for_weak():
    centres, rates, _ = upsolve.solve_curves(1900)
    easy = rates[:, 0]
    assert float(np.interp(2000, centres, easy)) > float(np.interp(800, centres, easy))
