"""Anomaly detection via section embedding drift.

Compares the current filing's section embedding against the historical mean
for that company+form_type+section.  Flags sections where the cosine distance
from the historical mean exceeds 2 standard deviations.

Depends on the semantic module for encoding and the section_embeddings table
in storage for historical data.
"""

import logging
from dataclasses import dataclass, field

import numpy as np

from redline.core import config
from redline.data import storage

logger = logging.getLogger(__name__)



@dataclass
class AnomalyResult:
    """Output of detect_anomaly()."""
    is_anomaly: bool = False
    cosine_distance: float | None = None
    mean_distance: float | None = None
    std_distance: float | None = None
    z_score: float | None = None
    history_count: int = 0


def compute_section_embedding(text: str) -> np.ndarray | None:
    """Compute the mean embedding for a section's text.

    Returns a 1-D numpy array (the mean of all sentence embeddings),
    or None if encoding fails.
    """
    from redline.analysis import semantic

    if not semantic.is_available():
        return None

    embeddings = semantic.encode_sentences([text])
    if embeddings is None or len(embeddings) == 0:
        return None

    # Mean of sentence embeddings → single section vector
    section_emb = embeddings.mean(axis=0)
    # L2-normalize
    norm = np.linalg.norm(section_emb)
    if norm > 0:
        section_emb = section_emb / norm
    return section_emb


def store_section_embedding(
    filing_id: str, section: str, embedding: np.ndarray
) -> None:
    """Persist a section embedding to the database."""
    storage.insert_section_embedding(
        filing_id=filing_id,
        section=section,
        embedding_bytes=embedding.tobytes(),
        model_name=config.EMBEDDING_MODEL,
    )


def detect_anomaly(
    cik: str,
    form_type: str,
    section: str,
    current_embedding: np.ndarray,
) -> AnomalyResult:
    """Compare *current_embedding* against historical mean for this company/section.

    Returns AnomalyResult with is_anomaly=True when cosine distance from the
    historical mean exceeds 2 standard deviations.
    """
    rows = storage.get_section_embeddings(
        cik=cik,
        form_type=form_type,
        section=section,
        model_name=config.EMBEDDING_MODEL,
    )

    if len(rows) < config.ANOMALY_MIN_HISTORY:
        logger.debug(
            "Anomaly detection skipped for %s/%s/%s: only %d historical embeddings",
            cik, form_type, section, len(rows),
        )
        return AnomalyResult(history_count=len(rows))

    # Reconstruct numpy arrays from stored blobs
    dim = len(current_embedding)
    historical = np.array(
        [np.frombuffer(row["embedding"], dtype=np.float32) for row in rows]
    )

    # Validate dimensions match
    if historical.shape[1] != dim:
        logger.warning(
            "Embedding dimension mismatch: current=%d, stored=%d",
            dim, historical.shape[1],
        )
        return AnomalyResult(history_count=len(rows))

    # Compute historical mean and normalize
    mean_emb = historical.mean(axis=0)
    norm = np.linalg.norm(mean_emb)
    if norm > 0:
        mean_emb = mean_emb / norm

    # Cosine distances: 1 - cosine_similarity
    historical_distances = np.array([
        1.0 - float(np.dot(emb / np.linalg.norm(emb), mean_emb))
        for emb in historical
    ])
    current_distance = 1.0 - float(np.dot(current_embedding, mean_emb))

    mean_dist = float(historical_distances.mean())
    std_dist = float(historical_distances.std())

    # Avoid division by zero — if all historical embeddings are identical
    if std_dist < 1e-10:
        z_score = 0.0 if abs(current_distance - mean_dist) < 1e-10 else float("inf")
    else:
        z_score = (current_distance - mean_dist) / std_dist

    is_anomaly = z_score > config.ANOMALY_Z_THRESHOLD

    if is_anomaly:
        logger.info(
            "ANOMALY detected: %s/%s/%s z=%.2f (dist=%.4f, mean=%.4f, std=%.4f)",
            cik, form_type, section, z_score,
            current_distance, mean_dist, std_dist,
        )

    return AnomalyResult(
        is_anomaly=is_anomaly,
        cosine_distance=current_distance,
        mean_distance=mean_dist,
        std_distance=std_dist,
        z_score=z_score,
        history_count=len(rows),
    )
