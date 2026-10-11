"""The prior-contest index, and the internal ratings it makes possible."""
import numpy as np
import pytest

from vrating.rating import cf
from vrating.sources import archive

MODERN = cf.NEW_ACCOUNT_RULE_START + 86400


def test_internal_offset_matches_the_promotion_schedule():
    """Displayed + offset must equal 1400 for an account that has never competed, and the
    offset must shrink by exactly each promotion as contests accumulate."""
    offsets = [cf.internal_offset(k, MODERN) for k in range(7)]
    assert offsets == [1400, 900, 550, 300, 150, 50, 0]
    steps = [a - b for a, b in zip(offsets, offsets[1:])]
    assert steps == list(cf.PROMOTIONS)
    assert sum(cf.PROMOTIONS) == cf.DEFAULT_RATING


def test_promotions_close_the_gap_exactly():
    """Six rounds of promotions take a displayed 0 to its internal 1400."""
    displayed = 0
    for k in range(6):
        displayed += cf.promotion(k, MODERN)
    assert displayed == cf.DEFAULT_RATING
    assert cf.internal_offset(6, MODERN) == 0


def test_prior_counts_absent_returns_none():
    assert archive.prior_counts(-12345) is None


@pytest.mark.gate
def test_archive_gives_plausible_counts_where_built():
    """Where the index exists it must be non-negative and align with the rated field."""
    from vrating.sources import cf as src
    if not archive.is_built():
        pytest.skip("archive not built")
    for cid in (1900, 2001):
        prior = archive.prior_counts(cid)
        if prior is None:
            continue
        changes = src.rating_changes(cid)
        assert len(prior) == len(changes["handles"])
        assert prior.min() >= 0
        # a big Div. 2 field always contains genuine first-timers and seasoned accounts
        assert (prior == 0).sum() > 50
        assert prior.max() > 50
