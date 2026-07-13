import math
from datetime import timedelta

import numpy as np
import pytest

from app.svix.correlation import calculate_correlation_matrix
from app.svix.engine import SVIXEngine
from app.svix.models import CorrelationMatrix
from app.svix.portfolio import calculate_portfolio_variance
from tests.svix.conftest import VALUATION_TIME, two_expiry_chain


def test_known_portfolio_variance_matches_w_transpose_sigma_w() -> None:
    correlation = CorrelationMatrix(assets=["A", "B"], matrix=[[1.0, 0.5], [0.5, 1.0]], observations=252)
    result = calculate_portfolio_variance({"A": 0.5, "B": 0.5}, {"A": 0.2, "B": 0.4}, correlation)
    expected = 0.5 ** 2 * 0.2 ** 2 + 0.5 ** 2 * 0.4 ** 2 + 2 * 0.5 * 0.5 * 0.2 * 0.4 * 0.5
    assert result.variance == pytest.approx(expected)


def test_engine_regression_fixture_calculates_full_svix() -> None:
    symbols = ("SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO")
    option_quotes = {symbol: two_expiry_chain(symbol) for symbol in symbols}
    returns = {symbol: (0.001 * np.sin(np.arange(260) / (index + 2)) + 0.0001 * index).tolist() for index, symbol in enumerate(symbols)}
    result = SVIXEngine().calculate(option_quotes, returns, VALUATION_TIME)
    assert result.svix > 0
    assert result.core_vol > 0
    assert result.memory_vol > 0
    assert result.ai_vol > 0
    assert math.isclose(sum(result.weights.values()), 1.0)
    assert len(result.correlation_matrix) == 6


def test_engine_reweights_when_newly_listed_memory_asset_is_unavailable() -> None:
    symbols = ("SOXX", "MU", "NVDA", "AMD", "AVGO")
    option_quotes = {symbol: [quote.model_copy(update={"delayed": True}) for quote in two_expiry_chain(symbol)] for symbol in symbols}
    returns = {symbol: (0.001 * np.sin(np.arange(260) / (index + 2)) + 0.0001 * index).tolist() for index, symbol in enumerate(symbols)}
    result = SVIXEngine().calculate(option_quotes, returns, VALUATION_TIME)
    assert "SKHY" not in result.weights
    assert math.isclose(sum(result.weights.values()), 1.0)
    assert result.memory_vol > 0
    assert 0 < result.calculation_quality < 0.65


def test_weighted_correlation_requires_historical_windows() -> None:
    with pytest.raises(Exception):
        calculate_correlation_matrix({"A": [0.01] * 60, "B": [0.02] * 60})


def test_approximate_engine_uses_spot_forward_and_single_valid_expiry() -> None:
    symbols = ("SOXX", "MU", "NVDA", "AMD", "AVGO")
    expiry = VALUATION_TIME + timedelta(days=24)
    option_quotes = {}
    for symbol in symbols:
        chain = two_expiry_chain(symbol)
        first_expiry = min(quote.expiry for quote in chain)
        sparse = [quote.model_copy(update={"delayed": True}) for quote in chain if quote.expiry == first_expiry and ((quote.option_type == "P" and quote.strike < 100) or (quote.option_type == "C" and quote.strike >= 100))]
        option_quotes[symbol] = [quote.model_copy(update={"expiry": expiry}) for quote in sparse]
    returns = {symbol: (0.001 * np.sin(np.arange(260) / (index + 2)) + 0.0001 * index).tolist() for index, symbol in enumerate(symbols)}
    result = SVIXEngine().calculate(option_quotes, returns, VALUATION_TIME, underlying_prices={symbol: 100.0 for symbol in symbols}, approximate=True)
    assert result.svix > 0
    assert result.estimated is True
    assert result.calculation_quality < 0.2
