"""Small provider-neutral helpers used while adapting external quote payloads."""

from __future__ import annotations

import math


def optional_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def optional_int(value: object) -> int | None:
    number = optional_float(value)
    return int(number) if number is not None and number >= 0 else None
