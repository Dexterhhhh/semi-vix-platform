"""Component and optional SOXX overlap-aware asset weights."""

from __future__ import annotations

from typing import Mapping

from app.svix.constants import AI_WEIGHTS, COMPONENT_WEIGHTS, CORE_WEIGHTS, MEMORY_WEIGHTS
from app.svix.models import DeOverlapResult


def combined_asset_weights() -> dict[str, float]:
    weights: dict[str, float] = {}
    for component_weight, allocation in ((COMPONENT_WEIGHTS["core"], CORE_WEIGHTS), (COMPONENT_WEIGHTS["memory"], MEMORY_WEIGHTS), (COMPONENT_WEIGHTS["ai"], AI_WEIGHTS)):
        for symbol, weight in allocation.items():
            weights[symbol] = weights.get(symbol, 0.0) + component_weight * weight
    return weights


def deoverlap_weights(original_weights: Mapping[str, float], soxx_constituent_exposure: Mapping[str, float] | None = None, etf_symbol: str = "SOXX") -> DeOverlapResult:
    """Remove duplicated direct-stock exposure implied by the SOXX allocation.

    The adjustment is optional because constituent weights are external input;
    without them the base component allocation remains unchanged.
    """
    original = {symbol.upper(): float(weight) for symbol, weight in original_weights.items()}
    if not soxx_constituent_exposure or etf_symbol not in original:
        return DeOverlapResult(original_weights=original, adjusted_weights=original, overlap_removed={})
    adjusted = dict(original)
    removed: dict[str, float] = {}
    etf_weight = original[etf_symbol]
    for symbol, exposure in soxx_constituent_exposure.items():
        normalized = symbol.upper()
        if normalized == etf_symbol or normalized not in adjusted:
            continue
        overlap = min(adjusted[normalized], max(0.0, etf_weight * float(exposure)))
        if overlap:
            adjusted[normalized] -= overlap
            removed[normalized] = overlap
    total = sum(adjusted.values())
    if total <= 0:
        raise ValueError("Overlap adjustment removed all asset weight")
    adjusted = {symbol: weight / total for symbol, weight in adjusted.items()}
    return DeOverlapResult(original_weights=original, adjusted_weights=adjusted, overlap_removed=removed)
