from datetime import timedelta

import pytest

from app.svix.exceptions import InvalidVariance, MissingExpiry
from app.svix.interpolation import interpolate_term_structure
from app.svix.models import VarianceResult
from app.svix.variance import calculate_expiry_variance
from tests.svix.conftest import VALUATION_TIME, make_chain


def test_synthetic_chain_produces_positive_stable_variance() -> None:
    expiry = VALUATION_TIME + timedelta(days=30)
    result = calculate_expiry_variance("NVDA", expiry, make_chain("NVDA", expiry), VALUATION_TIME)
    repeated = calculate_expiry_variance("NVDA", expiry, make_chain("NVDA", expiry), VALUATION_TIME)
    assert result.variance > 0
    assert result.variance == pytest.approx(repeated.variance)
    assert result.option_count == 3


def test_invalid_or_expired_chain_is_rejected() -> None:
    with pytest.raises(InvalidVariance):
        calculate_expiry_variance("NVDA", VALUATION_TIME - timedelta(days=1), [], VALUATION_TIME)


def test_interpolation_uses_variance_not_volatility() -> None:
    near = VarianceResult(symbol="NVDA", expiry=VALUATION_TIME + timedelta(days=20), variance=0.04, days_to_expiry=20, forward_price=100, option_count=3, quality_metrics={})
    far = VarianceResult(symbol="NVDA", expiry=VALUATION_TIME + timedelta(days=40), variance=0.16, days_to_expiry=40, forward_price=100, option_count=3, quality_metrics={})
    result = interpolate_term_structure("NVDA", [near, far], 30)
    assert result.variance == pytest.approx(0.10)
    assert result.volatility == pytest.approx(0.10 ** 0.5)
    with pytest.raises(MissingExpiry):
        interpolate_term_structure("NVDA", [near], 30)
