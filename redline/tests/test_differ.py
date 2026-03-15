"""Tests for redline.analysis.differ — sentence-level diffing.

Legacy mode tests verify exact backward compatibility with the original
SequenceMatcher algorithm.  Semantic mode tests use mocked embeddings
to verify the new cosine-similarity path.
"""

import pytest
from unittest.mock import patch, MagicMock

from redline.analysis.differ import diff_sections, _split_sentences
from redline.core import config
from redline.core.models import DiffResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def legacy_mode(monkeypatch):
    """Force legacy (SequenceMatcher) diff mode for deterministic tests."""
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", False)


# ---------------------------------------------------------------------------
# Sentence splitter tests (shared infrastructure)
# ---------------------------------------------------------------------------

def test_split_basic():
    sents = _split_sentences("Revenue grew 5%. Expenses declined. Net income rose.")
    assert len(sents) == 3
    assert sents[0] == "Revenue grew 5%."
    assert sents[1] == "Expenses declined."
    assert sents[2] == "Net income rose."


def test_split_abbreviations():
    """Known abbreviations like Inc. should not end a sentence."""
    sents = _split_sentences("Apple Inc. reported revenue. Profits grew.")
    assert len(sents) == 2
    assert "Inc." in sents[0]


def test_split_us_abbreviation():
    """U.S. is a common SEC filing abbreviation."""
    sents = _split_sentences("The company operates in the U.S. market. Revenue grew.")
    assert len(sents) == 2
    assert "U.S." in sents[0]


def test_split_empty():
    assert _split_sentences("") == []
    assert _split_sentences("   ") == []


def test_split_no_punctuation():
    """Text with no sentence-ending punctuation stays as one sentence."""
    sents = _split_sentences("revenue grew five percent")
    assert len(sents) == 1


# ---------------------------------------------------------------------------
# Legacy mode tests (original behavior preserved)
# ---------------------------------------------------------------------------

def test_identical_texts(legacy_mode):
    """Identical inputs produce zero changes."""
    text = "Revenue grew 5%. Expenses declined. Net income rose."
    result = diff_sections(text, text)
    assert isinstance(result, DiffResult)
    assert result.pct_changed == 0.0
    assert result.sentences_added == 0
    assert result.sentences_removed == 0
    assert result.sentences_unchanged == 3
    assert result.raw_chunks == []
    assert result.diff_preview == ""
    assert result.diff_version == 1


def test_minor_change(legacy_mode):
    """One sentence changed out of several keeps pct_changed small."""
    old = "Revenue grew 5%. Expenses declined. Net income rose. Cash was stable."
    new = "Revenue grew 5%. Expenses declined. Net income fell. Cash was stable."
    result = diff_sections(old, new)
    # 1 removed + 1 added out of 4 sentences
    assert result.sentences_removed == 1
    assert result.sentences_added == 1
    assert result.sentences_unchanged == 3
    assert 0 < result.pct_changed < 1.0
    # Should be 2/4 = 0.5
    assert abs(result.pct_changed - 0.5) < 1e-9


def test_major_change(legacy_mode):
    """Most sentences different gives a high pct_changed."""
    old = "Revenue grew. Margins expanded. Cash improved."
    new = "Revenue dropped. Margins shrank. Debt increased. Outlook negative."
    result = diff_sections(old, new)
    assert result.pct_changed > 0.5
    assert result.sentences_added > 0
    assert result.sentences_removed > 0


def test_old_empty(legacy_mode):
    """Old text empty, new has content — everything is added."""
    new = "Revenue grew 5%. Expenses declined. Net income rose."
    result = diff_sections("", new)
    assert result.sentences_added == 3
    assert result.sentences_removed == 0
    assert result.sentences_unchanged == 0
    assert result.pct_changed == 1.0
    assert result.word_count_old == 0
    assert result.word_count_new > 0
    assert result.word_count_delta > 0


def test_both_empty(legacy_mode):
    """Both texts empty — everything is zero."""
    result = diff_sections("", "")
    assert result.pct_changed == 0.0
    assert result.sentences_added == 0
    assert result.sentences_removed == 0
    assert result.sentences_unchanged == 0
    assert result.word_count_old == 0
    assert result.word_count_new == 0
    assert result.word_count_delta == 0
    assert result.diff_preview == ""
    assert result.raw_chunks == []


def test_preview_truncation(legacy_mode):
    """Preview must never exceed 3000 characters."""
    sent = "A" * 200
    old_sents = [f"{sent} old sentence number {i}." for i in range(100)]
    new_sents = [f"{sent} new sentence number {i}." for i in range(100)]
    old_text = " ".join(old_sents)
    new_text = " ".join(new_sents)
    result = diff_sections(old_text, new_text)
    assert len(result.diff_preview) <= 3000
    assert len(result.diff_preview) > 0


def test_word_counts(legacy_mode):
    """Word counts are computed correctly."""
    old = "one two three."
    new = "one two three four five."
    result = diff_sections(old, new)
    assert result.word_count_old == 3
    assert result.word_count_new == 5
    assert result.word_count_delta == 2


def test_raw_chunks_structure(legacy_mode):
    """raw_chunks entries have the required keys for non-equal blocks."""
    old = "Alpha. Beta. Gamma."
    new = "Alpha. Delta. Gamma."
    result = diff_sections(old, new)
    assert len(result.raw_chunks) >= 1
    required_keys = {
        "tag", "old_start", "old_end", "new_start", "new_end",
        "old_sentences", "new_sentences",
    }
    for chunk in result.raw_chunks:
        assert required_keys.issubset(chunk.keys())
        assert chunk["tag"] in ("insert", "delete", "replace")


# ---------------------------------------------------------------------------
# Semantic mode tests (mocked embeddings)
# ---------------------------------------------------------------------------

def test_semantic_fallback_when_unavailable(monkeypatch):
    """When semantic deps are missing, falls back to legacy mode."""
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)
    with patch("redline.analysis.semantic.is_available", return_value=False):
        result = diff_sections("Old text.", "New text.")
        assert result.diff_version == 1  # legacy


def test_semantic_fallback_on_encode_failure(monkeypatch):
    """If encoding fails, falls back to legacy."""
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)
    with patch("redline.analysis.semantic.is_available", return_value=True), \
         patch("redline.analysis.semantic.encode_sentences", return_value=None):
        result = diff_sections("Old text.", "New text.")
        assert result.diff_version == 1


def test_semantic_disabled_uses_legacy(monkeypatch):
    """When SEMANTIC_DIFF_ENABLED=False, always uses legacy."""
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", False)
    result = diff_sections("Some text.", "Some text.")
    assert result.diff_version == 1


def test_semantic_identical_texts(monkeypatch):
    """Semantic mode: identical texts produce zero changes."""
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)

    # Mock: identical text → identical embeddings → similarity 1.0
    def mock_encode(sentences):
        n = len(sentences)
        if n == 0:
            return np.array([]).reshape(0, 0)
        embs = np.eye(max(n, 3))[:n, :max(n, 3)]
        return embs

    with patch("redline.analysis.semantic.is_available", return_value=True), \
         patch("redline.analysis.semantic.encode_sentences", side_effect=mock_encode):
        text = "Revenue grew 5%. Expenses declined. Net income rose."
        result = diff_sections(text, text)
        assert result.diff_version == 2
        assert result.pct_changed == 0.0
        assert result.sentences_unchanged == 3
        assert result.sentences_added == 0
        assert result.sentences_removed == 0
        assert result.sentences_modified == 0
        assert result.semantic_similarity == pytest.approx(1.0)


def test_semantic_all_new(monkeypatch):
    """Semantic mode: empty old text → all sentences added."""
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)

    def mock_encode(sentences):
        n = len(sentences)
        if n == 0:
            return np.array([]).reshape(0, 0)
        return np.eye(max(n, 3))[:n, :max(n, 3)]

    with patch("redline.analysis.semantic.is_available", return_value=True), \
         patch("redline.analysis.semantic.encode_sentences", side_effect=mock_encode):
        result = diff_sections("", "Revenue grew. Expenses declined. Net income rose.")
        assert result.diff_version == 2
        assert result.sentences_added == 3
        assert result.sentences_removed == 0
        assert result.pct_changed == 1.0


def test_semantic_version_field(monkeypatch):
    """DiffResult from semantic mode has diff_version=2."""
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)

    def mock_encode(sentences):
        n = len(sentences)
        if n == 0:
            return np.array([]).reshape(0, 0)
        return np.eye(max(n, 4))[:n, :max(n, 4)]

    with patch("redline.analysis.semantic.is_available", return_value=True), \
         patch("redline.analysis.semantic.encode_sentences", side_effect=mock_encode):
        result = diff_sections("Alpha. Beta.", "Alpha. Gamma.")
        assert result.diff_version == 2
        assert result.semantic_similarity is not None


# ---------------------------------------------------------------------------
# Regression tests for P1/P2 bugs
# ---------------------------------------------------------------------------

def test_split_abbrev_end_of_sentence():
    """Abbreviation at end of sentence (followed by uppercase) should split."""
    sents = _split_sentences("The company operates in the U.S. Revenue grew.")
    assert len(sents) == 2
    assert sents[0] == "The company operates in the U.S."
    assert sents[1] == "Revenue grew."


def test_split_inc_end_of_sentence():
    """Inc. at end of a sentence followed by a new sentence should split."""
    sents = _split_sentences("Filed by Apple Inc. The report showed growth.")
    assert len(sents) == 2
    assert "Inc." in sents[0]
    assert sents[1] == "The report showed growth."


def test_semantic_modified_pct_weight(monkeypatch):
    """Semantic modified pair weighs same as legacy replace (2/total)."""
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)

    calls = []

    def mock_encode(sentences):
        n = len(sentences)
        if n == 0:
            return np.array([]).reshape(0, 0)
        embs = np.eye(max(n, 4))[:n, :max(n, 4)]
        calls.append(len(calls))
        if len(calls) == 2 and n >= 3:
            # Shift sentence[2] embedding to get ~0.7 similarity with old[2]
            embs[2] = np.array([0, 0, 0.7, np.sqrt(1 - 0.49)])
        return embs

    with patch("redline.analysis.semantic.is_available", return_value=True), \
         patch("redline.analysis.semantic.encode_sentences", side_effect=mock_encode):
        result = diff_sections(
            "Alpha. Beta. Gamma. Delta.",
            "Alpha. Beta. Changed. Delta.",
        )
        assert result.diff_version == 2
        assert result.sentences_modified == 1
        assert result.sentences_unchanged == 3
        # Modified pair counts as 2 changes (like legacy replace): 2/4 = 0.5
        assert result.pct_changed == pytest.approx(0.5)


def test_semantic_chunks_in_position_order(monkeypatch):
    """raw_chunks are in document position order, not grouped by type."""
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(config, "SEMANTIC_DIFF_ENABLED", True)

    call_count = [0]

    def mock_encode(sentences):
        n = len(sentences)
        if n == 0:
            return np.array([]).reshape(0, 0)
        call_count[0] += 1
        if call_count[0] == 1:
            # Old: A=[1,0,0,0,0,0], B=[0,1,0,0,0,0], C=[0,0,1,0,0,0]
            return np.eye(6)[:n, :6]
        else:
            # New: A=[1,0,0,0,0,0], D=[0,0,0,1,0,0], C=[0,0,1,0,0,0]
            embs = np.zeros((n, 6), dtype=float)
            embs[0] = [1, 0, 0, 0, 0, 0]  # matches old[0]
            embs[1] = [0, 0, 0, 1, 0, 0]  # orthogonal to all old
            embs[2] = [0, 0, 1, 0, 0, 0]  # matches old[2]
            return embs

    with patch("redline.analysis.semantic.is_available", return_value=True), \
         patch("redline.analysis.semantic.encode_sentences", side_effect=mock_encode):
        result = diff_sections("A. B. C.", "A. D. C.")
        assert result.diff_version == 2

        # Extract chunk tags in order
        tags = [c["tag"] for c in result.raw_chunks]
        # Should be position-sorted: equal(A), delete(B), insert(D), equal(C)
        assert tags == ["equal", "delete", "insert", "equal"]

        # Preview should also be in document order
        lines = result.diff_preview.split("\n")
        assert lines[0].startswith("- ")  # deleted B
        assert lines[1].startswith("+ ")  # added D
