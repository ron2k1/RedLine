"""Tests for redline.scorer -- preliminary_score and final_score."""

import pytest

from redline.models import DiffResult, SignalResult
from redline.scorer import final_score, preliminary_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _diff(pct_changed: float = 0.0) -> DiffResult:
    """Convenience builder for a DiffResult with only pct_changed set."""
    return DiffResult(
        pct_changed=pct_changed,
        word_count_old=1000,
        word_count_new=1000,
        word_count_delta=0,
        sentences_added=0,
        sentences_removed=0,
        sentences_unchanged=50,
        diff_preview="",
    )


def _signals(
    triggered: bool = False,
    max_severity: int = 0,
    signals: list[dict] | None = None,
) -> SignalResult:
    return SignalResult(
        triggered=triggered,
        signals=signals or [],
        max_severity=max_severity,
    )


# ---------------------------------------------------------------------------
# preliminary_score tests
# ---------------------------------------------------------------------------

class TestPreliminaryScore:
    def test_zero_change_no_signals(self):
        """pct_changed=0, no signals -> 1."""
        assert preliminary_score(_diff(0.0), _signals()) == 1

    def test_minor_change_no_signals(self):
        """pct_changed=0.10 -> base 2."""
        assert preliminary_score(_diff(0.10), _signals()) == 2

    def test_moderate_change_no_signals(self):
        """pct_changed=0.25 -> base 3."""
        assert preliminary_score(_diff(0.25), _signals()) == 3

    def test_large_change_no_signals(self):
        """pct_changed=0.45 -> base 5."""
        assert preliminary_score(_diff(0.45), _signals()) == 5

    def test_massive_change_no_signals(self):
        """pct_changed=0.80 -> base 6."""
        assert preliminary_score(_diff(0.80), _signals()) == 6

    def test_change_with_low_severity_signal(self):
        """base 2 + boost (4 // 2 = 2) -> 4."""
        diff = _diff(0.10)
        sig = _signals(triggered=True, max_severity=4, signals=[{"severity": 4}])
        assert preliminary_score(diff, sig) == 4

    def test_going_concern_forces_minimum_7(self):
        """Even with tiny pct_changed, severity-9 signal -> at least 7."""
        diff = _diff(0.01)  # base = 1
        sig = _signals(
            triggered=True,
            max_severity=9,
            signals=[{"severity": 9, "pattern": "going concern"}],
        )
        assert preliminary_score(diff, sig) >= 7

    def test_multiple_signals_uses_max_severity(self):
        """max_severity drives the boost, not individual signal severities."""
        diff = _diff(0.10)  # base = 2
        sig = _signals(
            triggered=True,
            max_severity=6,
            signals=[{"severity": 3}, {"severity": 6}],
        )
        # boost = 6 // 2 = 3 -> 2 + 3 = 5
        assert preliminary_score(diff, sig) == 5

    def test_clamped_to_10(self):
        """High change + high signal must not exceed 10."""
        diff = _diff(0.90)  # base = 6
        sig = _signals(
            triggered=True,
            max_severity=10,
            signals=[{"severity": 10}],
        )
        # 6 + 5 = 11 -> clamped to 10, also going-concern override (>=9) -> max(11,7) still clamped
        assert preliminary_score(diff, sig) == 10

    def test_boundary_pct_005(self):
        """pct_changed exactly at 0.05 boundary -> base 2 (not 1)."""
        assert preliminary_score(_diff(0.05), _signals()) == 2

    def test_boundary_pct_015(self):
        """pct_changed exactly at 0.15 boundary -> base 3."""
        assert preliminary_score(_diff(0.15), _signals()) == 3

    def test_boundary_pct_050(self):
        """pct_changed exactly at 0.50 boundary -> base 6."""
        assert preliminary_score(_diff(0.50), _signals()) == 6


# ---------------------------------------------------------------------------
# final_score tests
# ---------------------------------------------------------------------------

class TestFinalScore:
    def test_none_llm_returns_preliminary(self):
        """LLM not run -> pass preliminary through unchanged."""
        assert final_score(4, None) == 4

    def test_weighted_average(self):
        """preliminary=4, llm_severity=8 -> round(4*0.4 + 8*0.6) = round(6.4) = 6."""
        assert final_score(4, 8) == 6

    def test_weighted_average_rounds(self):
        """preliminary=3, llm_severity=7 -> round(3*0.4 + 7*0.6) = round(5.4) = 5."""
        assert final_score(3, 7) == 5

    def test_clamped_high(self):
        """Extreme inputs clamped to 10."""
        assert final_score(10, 10) == 10

    def test_clamped_low(self):
        """Very low inputs clamped to 1."""
        assert final_score(1, 1) == 1

    def test_llm_zero_clamps_to_1(self):
        """preliminary=1, llm_severity=0 -> round(0.4) = 0 -> clamped to 1."""
        assert final_score(1, 0) == 1

    def test_llm_dominates(self):
        """preliminary=2, llm_severity=10 -> round(0.8 + 6.0) = 7."""
        assert final_score(2, 10) == 7
