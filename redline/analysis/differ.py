"""Sentence-level structural differ using stdlib difflib.

Compares two plain-text sections sentence by sentence and returns a
DiffResult with change statistics, a human-readable preview, and raw
chunk data for downstream consumers.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from redline.core.models import DiffResult

_SENT_RE = re.compile(r"(?<=[.!?])(?:\s+|$)")

_MAX_PREVIEW = 3000


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences on '. ', '! ', '? ', or end-of-string
    following a sentence-ending punctuation mark.  Blank / whitespace-only
    fragments are discarded."""
    parts = _SENT_RE.split(text)
    return [s.strip() for s in parts if s and s.strip()]


def diff_sections(old_text: str, new_text: str) -> DiffResult:
    """Compare *old_text* and *new_text* at the sentence level.

    Returns a fully-populated ``DiffResult``.
    """
    old_sents = _split_sentences(old_text)
    new_sents = _split_sentences(new_text)

    matcher = SequenceMatcher(None, old_sents, new_sents, autojunk=False)

    added = 0
    removed = 0
    unchanged = 0
    raw_chunks: list[dict] = []
    preview_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        elif tag == "insert":
            added += j2 - j1
            raw_chunks.append(
                {
                    "tag": tag,
                    "old_start": i1,
                    "old_end": i2,
                    "new_start": j1,
                    "new_end": j2,
                    "old_sentences": [],
                    "new_sentences": new_sents[j1:j2],
                }
            )
            for s in new_sents[j1:j2]:
                preview_parts.append(f"+ {s}")
        elif tag == "delete":
            removed += i2 - i1
            raw_chunks.append(
                {
                    "tag": tag,
                    "old_start": i1,
                    "old_end": i2,
                    "new_start": j1,
                    "new_end": j2,
                    "old_sentences": old_sents[i1:i2],
                    "new_sentences": [],
                }
            )
            for s in old_sents[i1:i2]:
                preview_parts.append(f"- {s}")
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
            raw_chunks.append(
                {
                    "tag": tag,
                    "old_start": i1,
                    "old_end": i2,
                    "new_start": j1,
                    "new_end": j2,
                    "old_sentences": old_sents[i1:i2],
                    "new_sentences": new_sents[j1:j2],
                }
            )
            for s in old_sents[i1:i2]:
                preview_parts.append(f"- {s}")
            for s in new_sents[j1:j2]:
                preview_parts.append(f"+ {s}")

    total_old = len(old_sents)
    total_new = len(new_sents)
    denominator = max(total_old, total_new, 1)
    pct_changed = (added + removed) / denominator

    # Word counts (simple whitespace split)
    word_count_old = len(old_text.split())
    word_count_new = len(new_text.split())
    word_count_delta = word_count_new - word_count_old

    # Build preview, respecting the 3000-char cap
    diff_preview = _build_preview(preview_parts)

    return DiffResult(
        pct_changed=pct_changed,
        word_count_old=word_count_old,
        word_count_new=word_count_new,
        word_count_delta=word_count_delta,
        sentences_added=added,
        sentences_removed=removed,
        sentences_unchanged=unchanged,
        diff_preview=diff_preview,
        raw_chunks=raw_chunks,
    )


def _build_preview(parts: list[str]) -> str:
    """Join *parts* with newlines, truncating to ``_MAX_PREVIEW`` chars."""
    if not parts:
        return ""
    result: list[str] = []
    length = 0
    for part in parts:
        # +1 for the newline separator (except the first line)
        extra = len(part) + (1 if result else 0)
        if length + extra > _MAX_PREVIEW:
            remaining = _MAX_PREVIEW - length - (1 if result else 0)
            if remaining > 0:
                result.append(part[:remaining])
            break
        result.append(part)
        length += extra
    return "\n".join(result)
