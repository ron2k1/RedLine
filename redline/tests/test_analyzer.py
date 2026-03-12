"""Tests for redline.analyzer -- LLM analysis via Ollama/instructor.

All external calls are mocked; no real Ollama instance is needed.
"""

import pytest
from unittest.mock import patch, MagicMock

from redline.analyzer import AnalysisResponse, NotableChange, analyze_diff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_analysis_response():
    """Build a valid AnalysisResponse for mocking."""
    return AnalysisResponse(
        summary="Revenue recognition policy changed materially.",
        notable_changes=[
            NotableChange(
                description="Shift from point-in-time to over-time revenue recognition",
                category="financial",
                severity=7,
                quote="Revenue is now recognized over the contract period",
            ),
        ],
        severity_score=7,
        reasoning="The revenue recognition change could materially impact reported earnings timing.",
    )


_CALL_KWARGS = dict(
    ticker="AAPL",
    form_type="10-K",
    period="2025-09-30",
    section="7",
    diff_preview="+ Revenue is now recognized over the contract period.",
    signals_json='[{"pattern": "revenue recognition", "severity": 5}]',
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAnalyzeDiffSuccess:
    """Mock the OpenAI client so instructor returns a valid AnalysisResponse."""

    @patch("redline.analyzer.OpenAI")
    @patch("redline.analyzer.instructor.from_openai")
    def test_returns_dict_with_expected_keys(self, mock_from_openai, mock_openai_cls):
        # Arrange: make the patched client return our mock response
        mock_patched = MagicMock()
        mock_from_openai.return_value = mock_patched
        mock_patched.chat.completions.create.return_value = _mock_analysis_response()

        # Act
        result = analyze_diff(**_CALL_KWARGS)

        # Assert
        assert result is not None
        assert "summary" in result
        assert "notable_changes" in result
        assert "severity_score" in result
        assert "reasoning" in result

    @patch("redline.analyzer.OpenAI")
    @patch("redline.analyzer.instructor.from_openai")
    def test_severity_score_is_int_in_range(self, mock_from_openai, mock_openai_cls):
        mock_patched = MagicMock()
        mock_from_openai.return_value = mock_patched
        mock_patched.chat.completions.create.return_value = _mock_analysis_response()

        result = analyze_diff(**_CALL_KWARGS)

        assert isinstance(result["severity_score"], int)
        assert 1 <= result["severity_score"] <= 10

    @patch("redline.analyzer.OpenAI")
    @patch("redline.analyzer.instructor.from_openai")
    def test_reasoning_is_populated(self, mock_from_openai, mock_openai_cls):
        mock_patched = MagicMock()
        mock_from_openai.return_value = mock_patched
        mock_patched.chat.completions.create.return_value = _mock_analysis_response()

        result = analyze_diff(**_CALL_KWARGS)

        assert result["reasoning"]
        assert len(result["reasoning"]) > 0

    @patch("redline.analyzer.OpenAI")
    @patch("redline.analyzer.instructor.from_openai")
    def test_notable_changes_are_dicts(self, mock_from_openai, mock_openai_cls):
        mock_patched = MagicMock()
        mock_from_openai.return_value = mock_patched
        mock_patched.chat.completions.create.return_value = _mock_analysis_response()

        result = analyze_diff(**_CALL_KWARGS)

        assert isinstance(result["notable_changes"], list)
        assert len(result["notable_changes"]) == 1
        change = result["notable_changes"][0]
        assert isinstance(change, dict)
        assert change["category"] == "financial"
        assert change["severity"] == 7


class TestAnalyzeDiffFailure:
    """LLM errors must be caught and return None."""

    @patch("redline.analyzer.OpenAI")
    @patch("redline.analyzer.instructor.from_openai")
    def test_returns_none_on_exception(self, mock_from_openai, mock_openai_cls):
        mock_patched = MagicMock()
        mock_from_openai.return_value = mock_patched
        mock_patched.chat.completions.create.side_effect = RuntimeError("connection refused")

        result = analyze_diff(**_CALL_KWARGS)

        assert result is None

    @patch("redline.analyzer.OpenAI")
    @patch("redline.analyzer.instructor.from_openai")
    def test_no_exception_propagated(self, mock_from_openai, mock_openai_cls):
        mock_patched = MagicMock()
        mock_from_openai.return_value = mock_patched
        mock_patched.chat.completions.create.side_effect = ValueError("unexpected error")

        # Must not raise
        result = analyze_diff(**_CALL_KWARGS)
        assert result is None

    @patch("redline.analyzer.OpenAI", side_effect=Exception("cannot create client"))
    def test_client_creation_failure(self, mock_openai_cls):
        """Even if OpenAI() constructor blows up, we get None."""
        result = analyze_diff(**_CALL_KWARGS)
        assert result is None
