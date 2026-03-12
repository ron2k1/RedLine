"""Tests for redline.differ — sentence-level structural diffing."""

from redline.differ import diff_sections
from redline.models import DiffResult


def test_identical_texts():
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


def test_minor_change():
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


def test_major_change():
    """Most sentences different gives a high pct_changed."""
    old = "Revenue grew. Margins expanded. Cash improved."
    new = "Revenue dropped. Margins shrank. Debt increased. Outlook negative."
    result = diff_sections(old, new)
    assert result.pct_changed > 0.5
    assert result.sentences_added > 0
    assert result.sentences_removed > 0


def test_old_empty():
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


def test_both_empty():
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


def test_preview_truncation():
    """Preview must never exceed 3000 characters."""
    # Build a text with many long sentences so the diff preview would be huge
    sent = "A" * 200
    old_sents = [f"{sent} old sentence number {i}." for i in range(100)]
    new_sents = [f"{sent} new sentence number {i}." for i in range(100)]
    old_text = " ".join(old_sents)
    new_text = " ".join(new_sents)
    result = diff_sections(old_text, new_text)
    assert len(result.diff_preview) <= 3000
    # There should be *some* preview content since the texts differ
    assert len(result.diff_preview) > 0


def test_word_counts():
    """Word counts are computed correctly."""
    old = "one two three."
    new = "one two three four five."
    result = diff_sections(old, new)
    assert result.word_count_old == 3
    assert result.word_count_new == 5
    assert result.word_count_delta == 2


def test_raw_chunks_structure():
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
