"""Portfolio variance aggregation from asset volatility and correlation."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from app.svix.exceptions import InsufficientCorrelationData, InvalidVariance
from app.svix.models import CorrelationMatrix, PortfolioVarianceResult
from app.svix import go_engine


def calculate_portfolio_variance(weights: Mapping[str, float], volatilities: Mapping[str, float], correlation: CorrelationMatrix) -> PortfolioVarianceResult:
    if go_engine.enabled():
        try:
            result = go_engine.call("/v1/portfolio", {"weights": dict(weights), "volatilities": dict(volatilities), "correlation": correlation.model_dump()})
            return PortfolioVarianceResult.model_validate(result)
        except (ValueError, RuntimeError) as exc:
            raise InvalidVariance(str(exc)) from exc
    assets = correlation.assets
    if set(weights) != set(assets) or set(volatilities) != set(assets):
        raise InsufficientCorrelationData("Weights, volatilities, and correlation assets must match")
    vector = np.asarray([weights[asset] for asset in assets], dtype=float)
    sigma = np.asarray([volatilities[asset] for asset in assets], dtype=float)
    matrix = np.asarray(correlation.matrix, dtype=float)
    if matrix.shape != (len(assets), len(assets)) or not np.all(np.isfinite(matrix)):
        raise InsufficientCorrelationData("Correlation matrix dimensions are invalid")
    if not np.isclose(vector.sum(), 1.0, atol=1e-9) or np.any(vector < 0) or np.any(sigma < 0):
        raise InvalidVariance("Portfolio weights must be normalized and volatilities non-negative")
    covariance = np.outer(sigma, sigma) * matrix
    contributions = vector * (covariance @ vector)
    variance = float(vector @ covariance @ vector)
    if variance < -1e-12:
        raise InvalidVariance("Portfolio covariance produced a negative variance")
    variance = max(0.0, variance)
    return PortfolioVarianceResult(variance=variance, volatility=float(np.sqrt(variance)), component_contribution={asset: float(value) for asset, value in zip(assets, contributions)})
