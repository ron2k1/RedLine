# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Redline is a local SEC filing change detection tool for Windows. Polls EDGAR for 10-K/10-Q filings, extracts key sections, diffs at sentence level, detects financial red flag patterns, runs LLM analysis via Ollama, stores in SQLite, displays via Flask. Runs locally, uses no paid APIs, depends only on SEC's public endpoints.

## Commands

```bash
python -m redline.pipeline                     # run full pipeline
python -m redline.web.app                      # Flask UI on localhost:5000
pytest redline/tests/                          # all tests
pytest redline/tests/test_differ.py::test_name # single test
python -c "from redline.data.storage import init_db; init_db()"  # init DB
pip install -r requirements.txt
```

## Architecture

```
redline/
├── core/           # models.py (data contracts), config.py (env settings)
├── ingestion/      # edgar.py (SEC API), extractor.py (section extraction)
├── analysis/       # differ.py, signals.py, scorer.py, analyzer.py
├── data/           # storage.py (SQLite), watchlist.py (ticker management)
├── pipeline.py     # master orchestration (entry point)
├── web/            # Flask UI (app.py, templates/, static/)
└── tests/          # 104 tests
```

**Pipeline flow** (`pipeline.py`):
1. Resume stranded filings (`get_unprocessed_filings()` where `processed=0`)
2. Load watchlist → per ticker, per form_type: backfill (5yr) or poll for new
3. `process_filing()` — single function for backfill, daily, and crash-resume paths:
   extract sections → insert extraction attempts → diff against previous → score → maybe LLM → store

**Shared contracts** (`core/models.py`): `FilingRecord`, `ExtractionResult`, `DiffResult`, `SignalResult`. All modules use these — never ad-hoc dicts.

**Canonical key:** `filing_id` (accession number, dashes removed) is the one key for all storage APIs.

**Module ownership:**
- `data/storage.py` — sole SQLite access. 5 tables: companies, filings, sections, diffs, extraction_attempts
- `analysis/scorer.py` — sole owner of `preliminary_score()` and `final_score()`. Analyzer does NOT compute scores.
- `data/watchlist.py` — sole owner of watchlist.json. Normalizes tickers (BRK.B → BRK-B). Atomic writes.
- `core/config.py` — all settings from `.env`. Key: `SEC_USER_AGENT` (required by EDGAR), `OLLAMA_MODEL` (default qwen2.5:14b)

**Backfill:** Per (ticker, form_type). Detected by `get_filing_count() == 0`. Fetches 5 years including paginated SEC submission fragments via `files` array. Processes oldest→newest. `get_previous_filing(cik, form_type, before_period)` finds diff baseline.

**Crash recovery:** Interrupted runs leave `processed=0` filings. Next run resumes them via `get_unprocessed_filings()` before polling new. Diffs table has `UNIQUE(filing_id, prev_filing_id, section)` to prevent duplicates on retry.

**Web UI** (Flask, pure HTML+CSS):
- `/` — Dashboard: diffs only, color-coded scores
- `/company/<ticker>` — All filings (including extraction failures), extraction badges per section
- `/diff/<diff_id>` — Diff detail with sibling extraction statuses
- `/watchlist` — CRUD via watchlist.py module
