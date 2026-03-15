# Redline Change Primer

Running log of upgrades, fixes, and architectural changes. Newest first.

---

## 2026-03-15 — Upgrade 1: Semantic Diff Engine

**What changed:** Replaced `difflib.SequenceMatcher` with sentence embeddings + cosine similarity as the primary diff algorithm. Legacy SequenceMatcher preserved as automatic fallback.

### New files
- `redline/analysis/semantic.py` — Embedding engine. Lazy singleton model load, batch encoding, greedy bipartite matching, L2-normalized dot product for cosine similarity.
- `redline/tests/test_semantic.py` — 17 tests for similarity matrix, matching algorithm, edge cases.

### Modified files
- `redline/analysis/differ.py` — Two-mode architecture: `_diff_semantic()` (primary) + `_diff_legacy()` (fallback). Abbreviation-aware sentence splitter. Position-sorted preview output.
- `redline/core/config.py` — 7 new env-configurable settings: `EMBEDDING_MODEL`, `SEMANTIC_DIFF_ENABLED`, thresholds, batch size, `STORE_EMBEDDINGS`.
- `redline/core/models.py` — 3 new fields on `DiffResult`: `diff_version`, `semantic_similarity`, `sentences_modified` (all backward-compatible defaults).
- `redline/data/storage.py` — Idempotent migration system (`_run_migrations`). 3 new columns on `diffs` table, `section_embeddings` table (for future Upgrade 3), 4 performance indices.
- `redline/pipeline.py` — `diff_dict` now includes `diff_version`, `semantic_similarity`, `sentences_modified`.
- `requirements.txt` — Added `sentence-transformers>=2.2.0`, `scikit-learn>=1.0`.

### Bug fixes (same session)
1. **pct_changed under-reporting** — Semantic modified pairs counted as 1 change instead of 2 (legacy replace counts removed+added=2). Fixed: `modified * 2 + added + deleted` in numerator.
2. **Abbreviation over-protection** — Blanket dot-replacement prevented real sentence splits (e.g. "U.S. Revenue grew." stayed as one sentence). Fixed: abbreviations only protected mid-sentence via regex lookahead `(?=\s+[a-z\d])`.
3. **Preview/chunks out of order** — Chunks were grouped by type (all modified, then all deleted, then all added). Fixed: position-sorted event list using `new_idx` for new-side events and `_deleted_sort_key()` for old-only deletions.

### Key design decisions
- Default model: `all-MiniLM-L6-v2` (80MB) over `bge-large-en` (1.3GB) for CPU feasibility.
- Lazy singleton load — model loads once on first diff, stays in memory.
- Graceful fallback chain: semantic unavailable/fails → SequenceMatcher, no crash.
- `diff_version=1` (legacy) vs `2` (semantic) stored in DB so old and new diffs coexist.
- All thresholds configurable via `.env` (unchanged: 0.85, changed: 0.55, batch: 64).
- `section_embeddings` table created now but not populated yet (gated by `STORE_EMBEDDINGS=false`, ready for Upgrade 3).

### Test coverage
- 156 total tests passing (up from ~104 before Upgrade 1).
- 23 differ tests (8 legacy, 6 semantic, 5 splitter, 4 regression).
- 17 semantic engine tests (similarity matrix, matching, thresholds, greedy correctness).

---

## Planned Upgrades

| # | Name | Status |
|---|------|--------|
| 1 | Semantic diff (embeddings + cosine similarity) | Done |
| 2 | Context-aware signal detection (NLP over regex) | Not started |
| 3 | Multi-stage scoring with anomaly detection | Not started (DB schema ready) |
| 4 | Rich interactive dashboard | Not started |
| 5 | Extraction hardening + PDF support | Not started |
