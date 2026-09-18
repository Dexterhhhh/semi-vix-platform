from datetime import timedelta

import pytest

from app.svix.exceptions import InsufficientOptionData, InvalidVariance, MissingExpiry
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
    assert result.variance == pytest.approx(0.12)
    assert result.volatility == pytest.approx(0.12 ** 0.5)
    with pytest.raises(MissingExpiry):
        interpolate_term_structure("NVDA", [near], 30)


def test_nearest_expiry_fallback_has_a_bounded_distance() -> None:
    far_away = VarianceResult(symbol="NVDA", expiry=VALUATION_TIME + timedelta(days=180), variance=0.04, days_to_expiry=180, forward_price=100, option_count=3, quality_metrics={})
    with pytest.raises(MissingExpiry, match="more than 7 days"):
        interpolate_term_structure("NVDA", [far_away], 30, allow_nearest_fallback=True)


def test_true_k0_missing_a_leg_is_rejected() -> None:
    expiry = VALUATION_TIME + timedelta(days=30)
    chain = make_chain("NVDA", expiry)
    # Put-call parity implies F=106, so 105 is the true K0 even though it only
    # has a put.  The engine must not silently move K0 down to 100.
    template = chain[1]
    chain = [quote for quote in chain if quote.strike != 110]
    chain.append(template.model_copy(update={"contract_id": "TEST:NVDA:105:P", "strike": 105.0, "bid": 2.0, "ask": 2.2}))
    chain = [quote.model_copy(update={"bid": quote.bid + 4 if quote.strike == 100 and quote.option_type == "C" else quote.bid, "ask": quote.ask + 4 if quote.strike == 100 and quote.option_type == "C" else quote.ask}) for quote in chain]
    with pytest.raises(InsufficientOptionData, match="K0 requires both"):
        calculate_expiry_variance("NVDA", expiry, chain, VALUATION_TIME)
