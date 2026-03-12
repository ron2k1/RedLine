"""Scorer module -- single source of truth for all scoring in Redline.

Two entry points:
  preliminary_score(diff, signals) -> int   (1-10)
  final_score(preliminary, llm_severity)    (1-10)
"""

from __future__ import annotations

from redline.models import DiffResult, SignalResult


def preliminary_score(diff: DiffResult, signals: SignalResult) -> int:
    """Compute preliminary score 1-10 based on diff metrics and signal severity.

    Scoring logic:
    - Base score derived from pct_changed thresholds.
    - Signal boost: max_severity // 2 added when signals are triggered.
    - Going-concern override: any signal with severity >= 9 forces minimum 7.
    - Result clamped to [1, 10].
    """
    # --- base from pct_changed ---
    pct = diff.pct_changed
    if pct < 0.05:
        base = 1
    elif pct < 0.15:
        base = 2
    elif pct < 0.30:
        base = 3
    elif pct < 0.50:
        base = 5
    else:
        base = 6

    # --- signal boost ---
    score = base
    if signals.triggered:
        score += signals.max_severity // 2

    # --- going-concern override ---
    if any(s.get("severity", 0) >= 9 for s in signals.signals):
        score = max(score, 7)

    # --- clamp ---
    return max(1, min(10, score))


def final_score(preliminary: int, llm_severity: int | None) -> int:
    """Combine preliminary score with optional LLM severity.

    If llm_severity is None the preliminary score passes through unchanged.
    Otherwise a 40/60 weighted average is used, clamped to [1, 10].
    """
    if llm_severity is None:
        return preliminary

    combined = round(preliminary * 0.4 + llm_severity * 0.6)
    return max(1, min(10, combined))
