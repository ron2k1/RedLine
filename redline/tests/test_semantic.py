"""Tests for redline.analysis.semantic — embedding engine.

Tests the matching algorithm with synthetic numpy arrays — no model
download or GPU required.  The test file is skipped entirely if numpy
is not installed.
"""

import pytest

np = pytest.importorskip("numpy")

from redline.analysis.semantic import (
    semantic_match,
    compute_similarity_matrix,
    is_available,
    reset,
)
from redline.core import config


@pytest.fixture(autouse=True)
def clean_state():
    """Reset semantic module state between tests."""
    reset()
    yield
    reset()


# ---------------------------------------------------------------------------
# compute_similarity_matrix
# ---------------------------------------------------------------------------

def test_sim_matrix_identical():
    """Identical normalised vectors → diagonal of 1s."""
    embs = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    sim = compute_similarity_matrix(embs, embs)
    assert sim.shape == (3, 3)
    np.testing.assert_allclose(np.diag(sim), [1.0, 1.0, 1.0])
    # Off-diagonal should be 0
    np.testing.assert_allclose(sim[0, 1], 0.0, atol=1e-10)


def test_sim_matrix_orthogonal():
    """Orthogonal vectors → similarity 0."""
    a = np.array([[1, 0, 0]], dtype=float)
    b = np.array([[0, 1, 0]], dtype=float)
    sim = compute_similarity_matrix(a, b)
    np.testing.assert_allclose(sim[0, 0], 0.0, atol=1e-10)


def test_sim_matrix_empty_a():
    """Empty first input → (0, 0) matrix."""
    a = np.array([]).reshape(0, 3)
    b = np.array([[1, 0, 0]], dtype=float)
    sim = compute_similarity_matrix(a, b)
    assert sim.shape == (0, 0)


def test_sim_matrix_empty_b():
    a = np.array([[1, 0, 0]], dtype=float)
    b = np.array([]).reshape(0, 3)
    sim = compute_similarity_matrix(a, b)
    assert sim.shape == (0, 0)


def test_sim_matrix_known_value():
    """Two vectors at known angle have predictable cosine similarity."""
    a = np.array([[1, 0, 0]], dtype=float)
    # b = [cos(60°), sin(60°), 0] → cosine similarity = cos(60°) = 0.5
    b = np.array([[0.5, np.sqrt(3) / 2, 0]], dtype=float)
    sim = compute_similarity_matrix(a, b)
    np.testing.assert_allclose(sim[0, 0], 0.5, atol=1e-10)


# ---------------------------------------------------------------------------
# semantic_match — edge cases
# ---------------------------------------------------------------------------

def test_match_both_empty():
    result = semantic_match([], [], np.array([]), np.array([]))
    assert result["unchanged"] == []
    assert result["modified"] == []
    assert result["added"] == []
    assert result["deleted"] == []
    assert result["avg_similarity"] == 1.0


def test_match_empty_old():
    """No old sentences → all new are added."""
    new_embs = np.eye(2)
    result = semantic_match(
        [], ["a", "b"],
        np.array([]).reshape(0, 2), new_embs,
    )
    assert len(result["added"]) == 2
    assert len(result["deleted"]) == 0
    assert result["avg_similarity"] == 0.0


def test_match_empty_new():
    """No new sentences → all old are deleted."""
    old_embs = np.eye(2)
    result = semantic_match(
        ["a", "b"], [],
        old_embs, np.array([]).reshape(0, 2),
    )
    assert len(result["deleted"]) == 2
    assert len(result["added"]) == 0
    assert result["avg_similarity"] == 0.0


# ---------------------------------------------------------------------------
# semantic_match — identical embeddings
# ---------------------------------------------------------------------------

def test_match_identical():
    """Same embeddings → all unchanged, similarity 1.0."""
    embs = np.eye(3)
    result = semantic_match(
        ["a", "b", "c"], ["a", "b", "c"],
        embs, embs,
    )
    assert len(result["unchanged"]) == 3
    assert len(result["modified"]) == 0
    assert len(result["added"]) == 0
    assert len(result["deleted"]) == 0
    assert result["avg_similarity"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# semantic_match — completely different
# ---------------------------------------------------------------------------

def test_match_all_different():
    """Orthogonal embeddings → all added/deleted (below changed_threshold)."""
    old_embs = np.zeros((3, 6), dtype=float)
    old_embs[0, 0] = old_embs[1, 1] = old_embs[2, 2] = 1.0
    new_embs = np.zeros((3, 6), dtype=float)
    new_embs[0, 3] = new_embs[1, 4] = new_embs[2, 5] = 1.0

    result = semantic_match(
        ["a", "b", "c"], ["d", "e", "f"],
        old_embs, new_embs,
    )
    assert len(result["unchanged"]) == 0
    assert len(result["modified"]) == 0
    assert len(result["added"]) == 3
    assert len(result["deleted"]) == 3


# ---------------------------------------------------------------------------
# semantic_match — threshold classification
# ---------------------------------------------------------------------------

def test_match_above_unchanged_threshold():
    """Similarity >= unchanged_threshold → classified as unchanged."""
    old_embs = np.array([[1.0, 0.0, 0.0]])
    # Similarity = 0.9, above default unchanged_threshold (0.85)
    new_embs = np.array([[0.9, np.sqrt(1 - 0.81), 0.0]])

    result = semantic_match(
        ["old"], ["new"],
        old_embs, new_embs,
        unchanged_threshold=0.85,
        changed_threshold=0.55,
    )
    assert len(result["unchanged"]) == 1
    assert len(result["modified"]) == 0


def test_match_between_thresholds():
    """changed_threshold <= similarity < unchanged_threshold → modified."""
    old_embs = np.array([[1.0, 0.0, 0.0]])
    # Similarity = 0.7, between thresholds
    new_embs = np.array([[0.7, np.sqrt(1 - 0.49), 0.0]])

    result = semantic_match(
        ["old"], ["new"],
        old_embs, new_embs,
        unchanged_threshold=0.85,
        changed_threshold=0.55,
    )
    assert len(result["modified"]) == 1
    assert len(result["unchanged"]) == 0
    sim = result["modified"][0][2]
    assert 0.69 < sim < 0.71


def test_match_below_changed_threshold():
    """Similarity < changed_threshold → added + deleted (no match)."""
    old_embs = np.array([[1.0, 0.0, 0.0]])
    # Similarity = 0.3, below changed_threshold (0.55)
    new_embs = np.array([[0.3, np.sqrt(1 - 0.09), 0.0]])

    result = semantic_match(
        ["old"], ["new"],
        old_embs, new_embs,
        unchanged_threshold=0.85,
        changed_threshold=0.55,
    )
    assert len(result["added"]) == 1
    assert len(result["deleted"]) == 1
    assert len(result["unchanged"]) == 0
    assert len(result["modified"]) == 0


# ---------------------------------------------------------------------------
# semantic_match — greedy matching correctness
# ---------------------------------------------------------------------------

def test_match_greedy_pairs_highest_first():
    """Greedy matching should pair highest-similarity pairs first."""
    # Old: [1,0,0], [0,1,0]
    # New: [0.8,0.2,0] (close to old[0]), [0.2,0.8,0] (close to old[1])
    old_embs = np.array([[1, 0, 0], [0, 1, 0]], dtype=float)
    new_embs = np.array([[0.8, 0.2, 0], [0.2, 0.8, 0]], dtype=float)
    # Normalise new embeddings
    new_embs = new_embs / np.linalg.norm(new_embs, axis=1, keepdims=True)

    result = semantic_match(
        ["a", "b"], ["c", "d"],
        old_embs, new_embs,
        unchanged_threshold=0.99,   # force everything to "modified"
        changed_threshold=0.3,
    )
    # Both should be matched (not added/deleted)
    total_matched = len(result["unchanged"]) + len(result["modified"])
    assert total_matched == 2
    assert len(result["added"]) == 0
    assert len(result["deleted"]) == 0


def test_match_avoids_double_assignment():
    """Each old sentence is matched at most once."""
    # Two new sentences both similar to the same old sentence
    old_embs = np.array([[1, 0, 0]], dtype=float)
    new_embs = np.array([
        [0.9, np.sqrt(1 - 0.81), 0],  # sim ~0.9 to old[0]
        [0.8, np.sqrt(1 - 0.64), 0],  # sim ~0.8 to old[0]
    ], dtype=float)

    result = semantic_match(
        ["old"], ["new1", "new2"],
        old_embs, new_embs,
        unchanged_threshold=0.85,
        changed_threshold=0.55,
    )
    # old[0] should be matched to the higher-similarity new sentence
    total_matched = len(result["unchanged"]) + len(result["modified"])
    assert total_matched == 1
    assert len(result["added"]) == 1  # the lower-sim new sentence is unmatched


# ---------------------------------------------------------------------------
# semantic_match — avg_similarity
# ---------------------------------------------------------------------------

def test_avg_similarity_calculation():
    """avg_similarity is the mean of all matched pair similarities."""
    old_embs = np.array([[1, 0, 0], [0, 1, 0]], dtype=float)
    # new[0] identical to old[0] (sim=1.0), new[1] at 0.7 from old[1]
    new_embs = np.array([
        [1, 0, 0],
        [0.7, np.sqrt(1 - 0.49), 0],
    ], dtype=float)

    result = semantic_match(
        ["a", "b"], ["c", "d"],
        old_embs, new_embs,
        unchanged_threshold=0.85,
        changed_threshold=0.55,
    )
    # avg = (1.0 + 0.7) / 2 = 0.85
    assert result["avg_similarity"] == pytest.approx(0.85, abs=0.02)


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_returns_bool():
    """is_available returns a bool regardless of environment."""
    result = is_available()
    assert isinstance(result, bool)


def test_is_available_cached():
    """Second call returns same result without re-importing."""
    r1 = is_available()
    r2 = is_available()
    assert r1 == r2
