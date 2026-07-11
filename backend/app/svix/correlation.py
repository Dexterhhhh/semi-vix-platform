"""Weighted 60/120/252-day historical return correlation."""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from app.svix.constants import CORRELATION_WINDOWS, CORRELATION_WINDOW_WEIGHTS
from app.svix.exceptions import InsufficientCorrelationData
from app.svix.models import CorrelationMatrix


def calculate_returns(prices: Sequence[float]) -> list[float]:
    values = np.asarray(prices, dtype=float)
    if values.size < 2 or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise InsufficientCorrelationData("Prices must be finite, positive, and contain at least two observations")
    return np.diff(np.log(values)).tolist()


def calculate_correlation_matrix(returns_by_symbol: Mapping[str, Sequence[float]]) -> CorrelationMatrix:
    """Require 252 aligned returns, then blend 60/120/252 day correlations."""
    assets = sorted(returns_by_symbol)
    if len(assets) < 2:
        raise InsufficientCorrelationData("At least two assets are required for a correlation matrix")
    series = [np.asarray(returns_by_symbol[asset], dtype=float) for asset in assets]
    observations = min(item.size for item in series)
    if observations < max(CORRELATION_WINDOWS):
        raise InsufficientCorrelationData("At least 252 aligned historical returns are required")
    aligned = np.vstack([item[-observations:] for item in series])
    if not np.all(np.isfinite(aligned)):
        raise InsufficientCorrelationData("Historical returns contain non-finite values")
    blended = np.zeros((len(assets), len(assets)), dtype=float)
    for window in CORRELATION_WINDOWS:
        correlation = np.corrcoef(aligned[:, -window:])
        correlation = np.nan_to_num(correlation, nan=0.0)
        np.fill_diagonal(correlation, 1.0)
        blended += CORRELATION_WINDOW_WEIGHTS[window] * correlation
    blended = np.clip((blended + blended.T) / 2.0, -1.0, 1.0)
    np.fill_diagonal(blended, 1.0)
    return CorrelationMatrix(assets=assets, matrix=blended.tolist(), observations=observations)
