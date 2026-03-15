"""Sentence-level differ with semantic and legacy modes.

Primary mode: semantic diff using sentence embeddings (cosine similarity).
Fallback mode: structural diff using difflib.SequenceMatcher.

The fallback engages automatically when:
  - sentence-transformers is not installed
  - SEMANTIC_DIFF_ENABLED is False
  - the embedding model fails to load
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from redline.core import config
from redline.core.models import DiffResult

# ---------------------------------------------------------------------------
# Sentence splitting (shared by both modes)
# ---------------------------------------------------------------------------

# Common abbreviations in SEC filings that should NOT end a sentence.
_ABBREVIATIONS = [
    "Inc.", "Corp.", "Ltd.", "Co.", "Jr.", "Sr.", "Dr.", "Mr.", "Mrs.", "Ms.",
    "Prof.", "No.", "Vol.", "vs.", "Dept.", "Est.", "Approx.", "Rev.",
    "U.S.", "U.K.", "E.U.", "i.e.", "e.g.", "a.m.", "p.m.",
    "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.",
    "Sep.", "Oct.", "Nov.", "Dec.",
]

_ABBREV_PLACEHOLDER = "\x00"

_SENT_RE = re.compile(r"(?<=[.!?])\s+")

_MAX_PREVIEW = 3000


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences with abbreviation awareness.

    Protects known abbreviations (Inc., U.S., etc.) from being treated as
    sentence boundaries, then splits on standard sentence-ending punctuation
    followed by whitespace.
    """
    if not text or not text.strip():
        return []

    # Protect abbreviations only mid-sentence (followed by space + lowercase/digit).
    # When followed by space + uppercase, the abbreviation may genuinely end
    # the sentence (e.g. "in the U.S. Revenue grew." → two sentences).
    protected = text
    for abbr in _ABBREVIATIONS:
        placeholder = abbr.replace(".", _ABBREV_PLACEHOLDER)
        protected = re.sub(
            re.escape(abbr) + r"(?=\s+[a-z\d])",
            placeholder,
            protected,
        )

    parts = _SENT_RE.split(protected)

    # Restore dots and filter empties
    return [
        s.replace(_ABBREV_PLACEHOLDER, ".").strip()
        for s in parts
        if s and s.strip()
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diff_sections(old_text: str, new_text: str) -> DiffResult:
    """Compare *old_text* and *new_text*.

    Tries semantic mode (embeddings + cosine similarity) first.
    Falls back to legacy (SequenceMatcher) if unavailable or on failure.
    """
    if config.SEMANTIC_DIFF_ENABLED:
        # Lazy import — avoids loading torch at module import time
        from redline.analysis import semantic

        if semantic.is_available():
            result = _diff_semantic(old_text, new_text)
            if result is not None:
                return result

    return _diff_legacy(old_text, new_text)


# ---------------------------------------------------------------------------
# Semantic diff (Upgrade 1)
# ---------------------------------------------------------------------------

def _deleted_sort_key(old_idx: int, old_to_new: dict[int, int]) -> float:
    """Estimate new-text position for a deleted sentence.

    Looks backward for the nearest matched old sentence and places the
    deletion right after it (+0.5).  Falls back to -0.5 so orphaned
    deletions sort before all new-text content.
    """
    for i in range(old_idx - 1, -1, -1):
        if i in old_to_new:
            return old_to_new[i] + 0.5
    return -0.5


def _diff_semantic(old_text: str, new_text: str) -> DiffResult | None:
    """Semantic diff using sentence embeddings.  Returns None on failure."""
    from redline.analysis import semantic

    old_sents = _split_sentences(old_text)
    new_sents = _split_sentences(new_text)

    # Encode
    old_embs = semantic.encode_sentences(old_sents)
    new_embs = semantic.encode_sentences(new_sents)
    if old_embs is None or new_embs is None:
        return None  # model load failed; caller uses legacy

    # Handle both-empty
    if len(old_sents) == 0 and len(new_sents) == 0:
        return DiffResult(
            pct_changed=0.0,
            word_count_old=0, word_count_new=0, word_count_delta=0,
            sentences_added=0, sentences_removed=0, sentences_unchanged=0,
            diff_preview="", raw_chunks=[],
            diff_version=2, semantic_similarity=1.0, sentences_modified=0,
        )

    match_result = semantic.semantic_match(
        old_sents, new_sents, old_embs, new_embs,
    )

    unchanged = match_result["unchanged"]
    modified = match_result["modified"]
    added_indices = match_result["added"]
    deleted_indices = match_result["deleted"]

    # --- Build old_idx → new_idx map for positioning deletions ---
    old_to_new: dict[int, int] = {}
    for new_idx, old_idx, _sim in unchanged:
        old_to_new[old_idx] = new_idx
    for new_idx, old_idx, _sim in modified:
        old_to_new[old_idx] = new_idx

    # --- Build position-sorted event list ---
    # Each event: (sort_key, tiebreak, chunk_dict, preview_lines)
    events: list[tuple[float, int, dict, list[str]]] = []

    for new_idx, old_idx, sim in unchanged:
        events.append((float(new_idx), len(events), {
            "tag": "equal",
            "similarity": round(sim, 3),
            "old_sentences": [old_sents[old_idx]],
            "new_sentences": [new_sents[new_idx]],
        }, []))

    for new_idx, old_idx, sim in modified:
        events.append((float(new_idx), len(events), {
            "tag": "replace",
            "similarity": round(sim, 3),
            "old_sentences": [old_sents[old_idx]],
            "new_sentences": [new_sents[new_idx]],
        }, [
            f"- {old_sents[old_idx]}",
            f"+ {new_sents[new_idx]}",
        ]))

    for new_idx in added_indices:
        events.append((float(new_idx), len(events), {
            "tag": "insert",
            "old_sentences": [],
            "new_sentences": [new_sents[new_idx]],
        }, [f"+ {new_sents[new_idx]}"]))

    for old_idx in deleted_indices:
        sort_key = _deleted_sort_key(old_idx, old_to_new)
        events.append((sort_key, len(events), {
            "tag": "delete",
            "old_sentences": [old_sents[old_idx]],
            "new_sentences": [],
        }, [f"- {old_sents[old_idx]}"]))

    events.sort(key=lambda e: (e[0], e[1]))

    raw_chunks = [e[2] for e in events]
    preview_parts: list[str] = []
    for e in events:
        preview_parts.extend(e[3])

    # --- metrics ---
    total = max(len(old_sents), len(new_sents), 1)
    # Each modified pair counts as 2 (remove + add) to match legacy replace weight
    pct_changed = (len(modified) * 2 + len(added_indices) + len(deleted_indices)) / total

    word_count_old = len(old_text.split())
    word_count_new = len(new_text.split())

    return DiffResult(
        pct_changed=pct_changed,
        word_count_old=word_count_old,
        word_count_new=word_count_new,
        word_count_delta=word_count_new - word_count_old,
        sentences_added=len(added_indices),
        sentences_removed=len(deleted_indices),
        sentences_unchanged=len(unchanged),
        sentences_modified=len(modified),
        diff_preview=_build_preview(preview_parts),
        raw_chunks=raw_chunks,
        diff_version=2,
        semantic_similarity=match_result["avg_similarity"],
    )


# ---------------------------------------------------------------------------
# Legacy diff (SequenceMatcher — original algorithm, preserved as fallback)
# ---------------------------------------------------------------------------

def _diff_legacy(old_text: str, new_text: str) -> DiffResult:
    """Structural diff using difflib.SequenceMatcher."""
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
            raw_chunks.append({
                "tag": tag,
                "old_start": i1, "old_end": i2,
                "new_start": j1, "new_end": j2,
                "old_sentences": [],
                "new_sentences": new_sents[j1:j2],
            })
            for s in new_sents[j1:j2]:
                preview_parts.append(f"+ {s}")
        elif tag == "delete":
            removed += i2 - i1
            raw_chunks.append({
                "tag": tag,
                "old_start": i1, "old_end": i2,
                "new_start": j1, "new_end": j2,
                "old_sentences": old_sents[i1:i2],
                "new_sentences": [],
            })
            for s in old_sents[i1:i2]:
                preview_parts.append(f"- {s}")
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
            raw_chunks.append({
                "tag": tag,
                "old_start": i1, "old_end": i2,
                "new_start": j1, "new_end": j2,
                "old_sentences": old_sents[i1:i2],
                "new_sentences": new_sents[j1:j2],
            })
            for s in old_sents[i1:i2]:
                preview_parts.append(f"- {s}")
            for s in new_sents[j1:j2]:
                preview_parts.append(f"+ {s}")

    total = max(len(old_sents), len(new_sents), 1)
    pct_changed = (added + removed) / total
    word_count_old = len(old_text.split())
    word_count_new = len(new_text.split())

    return DiffResult(
        pct_changed=pct_changed,
        word_count_old=word_count_old,
        word_count_new=word_count_new,
        word_count_delta=word_count_new - word_count_old,
        sentences_added=added,
        sentences_removed=removed,
        sentences_unchanged=unchanged,
        diff_preview=_build_preview(preview_parts),
        raw_chunks=raw_chunks,
        diff_version=1,
    )


# ---------------------------------------------------------------------------
# Preview builder (shared)
# ---------------------------------------------------------------------------

def _build_preview(parts: list[str]) -> str:
    """Join *parts* with newlines, stopping at sentence boundary near the cap.

    Never cuts mid-sentence — stops before the part that would exceed
    ``_MAX_PREVIEW`` characters.
    """
    if not parts:
        return ""
    result: list[str] = []
    length = 0
    for part in parts:
        extra = len(part) + (1 if result else 0)
        if length + extra > _MAX_PREVIEW:
            if not result:
                # First part alone exceeds cap — truncate it (rare edge case)
                result.append(part[:_MAX_PREVIEW])
            break
        result.append(part)
        length += extra
    return "\n".join(result)
