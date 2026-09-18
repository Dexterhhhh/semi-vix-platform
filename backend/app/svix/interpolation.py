"""30-calendar-day interpolation of annual variance, never volatility."""

from __future__ import annotations

import math
from typing import Iterable

from app.svix.exceptions import MissingExpiry
from app.svix import go_engine
from app.svix.models import TermStructureResult, VarianceResult


def _quality(result: VarianceResult) -> float:
    quality = result.quality_metrics.get("forward_quality", 0.0) * (1.0 - 0.2 * result.quality_metrics.get("k0_fallback", 0.0))
    if result.quality_metrics.get("spot_forward", 0.0):
        quality *= 0.7
    if result.quality_metrics.get("uncorrected_variance", 0.0):
        quality *= 0.5
    return quality


def interpolate_term_structure(
    symbol: str,
    variances: Iterable[VarianceResult],
    target_days: int = 30,
    allow_nearest_fallback: bool = False,
    max_fallback_distance_days: float = 7.0,
) -> TermStructureResult:
    """Interpolate *variance* between the two expiries bracketing target_days."""
    ordered = sorted(variances, key=lambda item: item.days_to_expiry)
    if not ordered:
        raise MissingExpiry("No valid expiries are available")
    exact = next((item for item in ordered if math.isclose(item.days_to_expiry, target_days, abs_tol=1e-9)), None)
    if exact:
        return TermStructureResult(symbol=symbol, target_days=target_days, variance=exact.variance, volatility=math.sqrt(exact.variance), near_expiry=exact.expiry, calculation_quality=_quality(exact))
    near = next((item for item in reversed(ordered) if item.days_to_expiry < target_days), None)
    next_expiry = next((item for item in ordered if item.days_to_expiry > target_days), None)
    if near is None or next_expiry is None:
        if allow_nearest_fallback:
            nearest = min(ordered, key=lambda item: abs(item.days_to_expiry - target_days))
            if abs(nearest.days_to_expiry - target_days) > max_fallback_distance_days:
                raise MissingExpiry(
                    f"Nearest expiry is more than {max_fallback_distance_days:g} days from target"
                )
            return TermStructureResult(symbol=symbol, target_days=target_days, variance=nearest.variance, volatility=math.sqrt(nearest.variance), near_expiry=nearest.expiry, calculation_quality=_quality(nearest) * 0.45)
        raise MissingExpiry(f"Target {target_days}D is not bracketed by valid expiries")
    weight_near = (next_expiry.days_to_expiry - target_days) / (next_expiry.days_to_expiry - near.days_to_expiry)
    # A variance swap accumulates variance over time.  Interpolate total
    # variance (T * sigma^2), then annualize at the target horizon.
    if go_engine.enabled():
        try:
            variance = float(go_engine.call("/v1/interpolate", {
                "near_days": near.days_to_expiry,
                "near_variance": near.variance,
                "far_days": next_expiry.days_to_expiry,
                "far_variance": next_expiry.variance,
                "target_days": target_days,
            })["variance"])
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise MissingExpiry(str(exc)) from exc
    else:
        variance = (
            weight_near * near.days_to_expiry * near.variance
            + (1.0 - weight_near) * next_expiry.days_to_expiry * next_expiry.variance
        ) / target_days
    if not math.isfinite(variance) or variance <= 0:
        raise MissingExpiry("Variance interpolation produced an invalid value")
    quality = weight_near * _quality(near) + (1.0 - weight_near) * _quality(next_expiry)
    return TermStructureResult(symbol=symbol, target_days=target_days, variance=variance, volatility=math.sqrt(variance), near_expiry=near.expiry, next_expiry=next_expiry.expiry, calculation_quality=quality)
