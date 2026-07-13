"""JSON-safe diagnostics and results emitted by the SVIX engine."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SVIXModel(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)


class ForwardResult(SVIXModel):
    forward_price: float = Field(gt=0)
    reference_strike: float = Field(gt=0)
    quality_score: float = Field(ge=0, le=1)
    pair_count: int = Field(ge=0)


class K0Result(SVIXModel):
    strike: float = Field(gt=0)
    used_nearest_fallback: bool = False


class FilteredOption(SVIXModel):
    strike: float = Field(gt=0)
    delta_k: float = Field(gt=0)
    option_price: float = Field(gt=0)
    option_type: str


class FilteredOptionSet(SVIXModel):
    symbol: str
    expiry: datetime
    k0: K0Result
    options: List[FilteredOption]
    forward: ForwardResult


class VarianceResult(SVIXModel):
    symbol: str
    expiry: datetime
    variance: float = Field(gt=0)
    days_to_expiry: float = Field(gt=0)
    forward_price: float = Field(gt=0)
    option_count: int = Field(ge=2)
    quality_metrics: Dict[str, float]


class TermStructureResult(SVIXModel):
    symbol: str
    target_days: int = Field(gt=0)
    variance: float = Field(gt=0)
    volatility: float = Field(gt=0)
    near_expiry: datetime
    next_expiry: Optional[datetime] = None
    calculation_quality: float = Field(default=1.0, ge=0, le=1)


class CorrelationMatrix(SVIXModel):
    assets: List[str]
    matrix: List[List[float]]
    observations: int = Field(gt=0)


class PortfolioVarianceResult(SVIXModel):
    variance: float = Field(ge=0)
    volatility: float = Field(ge=0)
    component_contribution: Dict[str, float]


class DeOverlapResult(SVIXModel):
    original_weights: Dict[str, float]
    adjusted_weights: Dict[str, float]
    overlap_removed: Dict[str, float]


class SVIXResult(SVIXModel):
    timestamp: datetime
    svix: float = Field(ge=0)
    core_vol: float = Field(ge=0)
    memory_vol: float = Field(ge=0)
    ai_vol: float = Field(ge=0)
    weights: Dict[str, float]
    correlation_matrix: List[List[float]]
    calculation_quality: float = Field(ge=0, le=1)
    estimated: bool = False
    source_feed: Optional[str] = None
