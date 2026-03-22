"""Embedding engine for semantic sentence comparison.

Lazy-loads a sentence-transformer model on first use.  Falls back gracefully
if dependencies (torch, sentence-transformers) are unavailable — the differ
will use SequenceMatcher instead.

Model is loaded once and kept in memory (singleton).  First run downloads
the model to ~/.cache/torch/sentence_transformers/ (automatic caching).
"""

import logging
from typing import Optional

from redline.core import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton state
# ---------------------------------------------------------------------------
_model = None
_load_attempted = False
_available: Optional[bool] = None


def is_available() -> bool:
    """Return True if semantic diff dependencies are importable."""
    global _available
    if _available is not None:
        return _available
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401
        _available = True
    except (ImportError, OSError, Exception) as exc:
        logger.info("Semantic diff unavailable (%s); will use SequenceMatcher", exc)
        _available = False
    return _available


def _get_model():
    """Lazy-load the embedding model.  Returns the model or None on failure."""
    global _model, _load_attempted
    if _model is not None:
        return _model
    if _load_attempted:
        return None
    _load_attempted = True

    if not is_available():
        return None

    try:
        from sentence_transformers import SentenceTransformer

        model_name = config.EMBEDDING_MODEL
        logger.info(
            "Loading embedding model '%s' (first run downloads to cache)...",
            model_name,
        )
        _model = SentenceTransformer(model_name)
        logger.info("Model loaded on device: %s", _model.device)
        return _model
    except Exception as exc:
        logger.warning("Failed to load embedding model: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode_sentences(sentences: list[str]):
    """Encode *sentences* into L2-normalised embeddings.

    Returns an (N, dim) numpy array, or None on failure.
    Batches internally according to ``config.EMBEDDING_BATCH_SIZE``.
    """
    import numpy as np

    model = _get_model()
    if model is None:
        return None
    if not sentences:
        return np.array([]).reshape(0, 0)

    try:
        embeddings = model.encode(
            sentences,
            batch_size=config.EMBEDDING_BATCH_SIZE,
            show_progress_bar=False,
            normalize_embeddings=True,  # L2-norm → dot product = cosine sim
        )
        return embeddings
    except Exception as exc:
        logger.error("Embedding encode failed: %s", exc)
        return None


def compute_similarity_matrix(embeddings_a, embeddings_b):
    """Cosine similarity matrix between two sets of L2-normalised embeddings.

    Returns shape ``(len(a), len(b))``.  Empty input → ``(0, 0)``.
    """
    import numpy as np

    if len(embeddings_a) == 0 or len(embeddings_b) == 0:
        return np.array([]).reshape(0, 0)
    # Dot product of L2-normalised vectors == cosine similarity
    return embeddings_a @ embeddings_b.T


def semantic_match(
    old_sentences: list[str],
    new_sentences: list[str],
    old_embeddings,
    new_embeddings,
    unchanged_threshold: float | None = None,
    changed_threshold: float | None = None,
) -> dict:
    """Match new sentences to old sentences by semantic similarity.

    Uses greedy bipartite matching — highest-similarity pairs first.

    Returns dict with keys:
        unchanged  — list of ``(new_idx, old_idx, similarity)`` (meaning preserved)
        modified   — list of ``(new_idx, old_idx, similarity)`` (meaning changed)
        added      — list of ``new_idx`` (no match in old)
        deleted    — list of ``old_idx`` (no match in new)
        avg_similarity — float, average similarity of all matched pairs
    """
    if unchanged_threshold is None:
        unchanged_threshold = config.SEMANTIC_UNCHANGED_THRESHOLD
    if changed_threshold is None:
        changed_threshold = config.SEMANTIC_CHANGED_THRESHOLD

    # --- edge cases ---
    if not old_sentences and not new_sentences:
        return {
            "unchanged": [], "modified": [], "added": [], "deleted": [],
            "avg_similarity": 1.0,
        }
    if not old_sentences:
        return {
            "unchanged": [], "modified": [],
            "added": list(range(len(new_sentences))), "deleted": [],
            "avg_similarity": 0.0,
        }
    if not new_sentences:
        return {
            "unchanged": [], "modified": [],
            "added": [], "deleted": list(range(len(old_sentences))),
            "avg_similarity": 0.0,
        }

    sim_matrix = compute_similarity_matrix(new_embeddings, old_embeddings)

    # --- greedy bipartite matching: pair highest-similarity first ---
    candidates = []
    for i in range(len(new_sentences)):
        for j in range(len(old_sentences)):
            sim = float(sim_matrix[i, j])
            if sim >= changed_threshold:
                candidates.append((sim, i, j))

    candidates.sort(reverse=True)

    matched_new: set[int] = set()
    matched_old: set[int] = set()
    unchanged: list[tuple] = []
    modified: list[tuple] = []

    for sim, new_idx, old_idx in candidates:
        if new_idx in matched_new or old_idx in matched_old:
            continue
        matched_new.add(new_idx)
        matched_old.add(old_idx)
        if sim >= unchanged_threshold:
            unchanged.append((new_idx, old_idx, sim))
        else:
            modified.append((new_idx, old_idx, sim))

    added = [i for i in range(len(new_sentences)) if i not in matched_new]
    deleted = [j for j in range(len(old_sentences)) if j not in matched_old]

    all_sims = [s for _, _, s in unchanged] + [s for _, _, s in modified]
    avg_similarity = sum(all_sims) / len(all_sims) if all_sims else 0.0

    return {
        "unchanged": unchanged,
        "modified": modified,
        "added": added,
        "deleted": deleted,
        "avg_similarity": avg_similarity,
    }


def reset():
    """Reset module state.  Useful in tests."""
    global _model, _load_attempted, _available
    _model = None
    _load_attempted = False
    _available = None
