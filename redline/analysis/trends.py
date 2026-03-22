"""Trend analysis — track score trajectories and pct_changed volatility.

Requires 4+ filing periods per (ticker, form_type, section) to compute.
Called after each filing is processed to update the trends table.
"""

import json
import logging
import math

from redline.core.models import TrendResult
from redline.data import storage

logger = logging.getLogger(__name__)

MIN_PERIODS = 4


def _linear_slope(values: list[float]) -> float:
    """Compute slope of simple linear regression (y = a + b*x).

    x is 0-indexed period number. Returns slope b.
    """
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _stddev(values: list[float]) -> float:
    """Population standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)


def _direction(slope: float) -> str:
    """Classify slope into direction label."""
    if slope > 0.3:
        return "worsening"
    elif slope < -0.3:
        return "improving"
    return "stable"


def compute_trend(ticker: str, form_type: str, section: str) -> TrendResult | None:
    """Compute trend for a specific ticker/form_type/section.

    Returns None if fewer than MIN_PERIODS data points exist.
    """
    history = storage.get_score_history(ticker, form_type, section)
    if len(history) < MIN_PERIODS:
        return None

    scores = [
        h["final_score"] if h["final_score"] is not None else h["preliminary_score"]
        for h in history
    ]
    pct_values = [h["pct_changed"] for h in history]

    slope = _linear_slope([float(s) for s in scores])
    direction = _direction(slope)
    pct_mean = sum(pct_values) / len(pct_values)
    pct_std = _stddev(pct_values)

    return TrendResult(
        ticker=ticker,
        form_type=form_type,
        section=section,
        periods=len(history),
        score_trend=scores,
        score_slope=round(slope, 3),
        score_latest=scores[-1],
        score_mean=round(sum(scores) / len(scores), 2),
        pct_changed_mean=round(pct_mean, 4),
        pct_changed_stddev=round(pct_std, 4),
        pct_changed_latest=pct_values[-1],
        direction=direction,
        volatile=pct_std > 0.10,
    )


def update_trend(ticker: str, form_type: str, section: str) -> TrendResult | None:
    """Compute and persist trend for a ticker/form_type/section.

    Returns the TrendResult if enough data, else None.
    """
    result = compute_trend(ticker, form_type, section)
    if result is None:
        return None

    data = {
        "periods": [
            {"period": h["period_of_report"],
             "score": h["final_score"] if h["final_score"] is not None else h["preliminary_score"],
             "pct_changed": h["pct_changed"]}
            for h in storage.get_score_history(ticker, form_type, section)
        ]
    }

    storage.upsert_trend({
        "ticker": result.ticker,
        "form_type": result.form_type,
        "section": result.section,
        "periods": result.periods,
        "score_trend": json.dumps(result.score_trend),
        "score_slope": result.score_slope,
        "score_latest": result.score_latest,
        "score_mean": result.score_mean,
        "pct_changed_mean": result.pct_changed_mean,
        "pct_changed_stddev": result.pct_changed_stddev,
        "pct_changed_latest": result.pct_changed_latest,
        "direction": result.direction,
        "volatile": 1 if result.volatile else 0,
        "data_json": json.dumps(data),
    })

    logger.info("Trend updated: %s %s %s — %s (slope=%.3f, %d periods)",
                ticker, form_type, section, result.direction,
                result.score_slope, result.periods)
    return result


def update_all_trends_for_ticker(ticker: str) -> list[TrendResult]:
    """Recompute trends for all form_type/section combos for a ticker."""
    diffs = storage.get_diffs_for_ticker(ticker)
    seen = set()
    results = []
    for d in diffs:
        key = (d["form_type"], d["section"])
        if key in seen:
            continue
        seen.add(key)
        result = update_trend(ticker, d["form_type"], d["section"])
        if result:
            results.append(result)
    return results
