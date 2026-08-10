"""Explain current resource use against the user's own prior measurements.

This module intentionally does statistics, not causal inference.  A baseline
describes what has been typical on this machine under comparable load; it never
claims that an agent caused a host-level memory change.
"""
from __future__ import annotations

from statistics import median
from typing import Dict, Iterable, List


def _percentile(values: List[float], fraction: float) -> float:
    """Linear-interpolated percentile for a non-empty sorted sequence."""
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] + (values[upper] - values[lower]) * weight


def assess_personal_baseline(
    current: float,
    historical: Iterable[float],
    minimum_samples: int = 20,
) -> Dict[str, float | int | str | None]:
    """Classify a measurement against comparable local observations.

    The normal band is the historical 10th–90th percentile.  Values above the
    90th percentile are ``unusual`` and values more than twice the typical
    (median) value are ``extreme``.  Until enough observations exist, the
    caller gets an explicit learning state rather than a misleading judgement.
    """
    values = sorted(float(value) for value in historical if float(value) >= 0)
    count = len(values)
    if not values:
        return {
            "state": "learning", "sample_count": 0, "typical": None,
            "range_low": None, "range_high": None, "ratio_to_typical": None,
        }

    typical = median(values)
    low = _percentile(values, 0.10)
    high = _percentile(values, 0.90)
    ratio = (float(current) / typical) if typical > 0 else None
    if count < minimum_samples:
        state = "learning"
    elif ratio is not None and ratio >= 2:
        state = "extreme"
    elif float(current) > high:
        state = "unusual"
    else:
        state = "normal"
    return {
        "state": state,
        "sample_count": count,
        "typical": round(typical, 2),
        "range_low": round(low, 2),
        "range_high": round(high, 2),
        "ratio_to_typical": round(ratio, 2) if ratio is not None else None,
    }
