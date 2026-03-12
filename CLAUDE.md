# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Redline is a local SEC filing change detection tool for Windows. Polls EDGAR for 10-K/10-Q filings, extracts key sections, diffs at sentence level, detects financial red flag patterns, runs LLM analysis via Ollama, stores in SQLite, displays via Flask. Everything runs locally — no cloud, no auth, no paid APIs.

## Commands

```bash
python -m redline.pipeline                     # run full pipeline
python -m redline.web.app                      # Flask UI on localhost:5000
pytest redline/tests/                          # all tests
pytest redline/tests/test_differ.py::test_name # single test
python -c "from redline.storage import init_db; init_db()"  # init DB
pip install -r requirements.txt
```

## Architecture

**Pipeline flow** (`pipeline.py`):
1. Resume stranded filings (`get_unprocessed_filings()` where `processed=0`)
2. Load watchlist → per ticker, per form_type: backfill (5yr) or poll for new
3. `process_filing()` — single function for backfill, daily, and crash-resume paths:
   extract sections → insert extraction attempts → diff against previous → score → maybe LLM → store

**Shared contracts** (`models.py`): `FilingRecord`, `ExtractionResult`, `DiffResult`, `SignalResult`. All modules use these — never ad-hoc dicts.

**Canonical key:** `filing_id` (accession number, dashes removed) is the one key for all storage APIs.

**Module ownership:**
- `storage.py` — sole SQLite access. 5 tables: companies, filings, sections, diffs, extraction_attempts
- `scorer.py` — sole owner of `preliminary_score()` and `final_score()`. Analyzer does NOT compute scores.
- `watchlist.py` — sole owner of watchlist.json. Normalizes tickers (BRK.B → BRK-B). Atomic writes.
- `config.py` — all settings from `.env`. Key: `SEC_USER_AGENT` (required by EDGAR), `OLLAMA_MODEL` (default qwen2.5:13b-instruct)

**Backfill:** Per (ticker, form_type). Detected by `get_filing_count() == 0`. Fetches 5 years including paginated SEC submission fragments via `files` array. Processes oldest→newest. `get_previous_filing(cik, form_type, before_period)` finds diff baseline.

**Crash recovery:** Interrupted runs leave `processed=0` filings. Next run resumes them via `get_unprocessed_filings()` before polling new.

**Web UI** (Flask, pure HTML+CSS):
- `/` — Dashboard: diffs only, color-coded scores
- `/company/<ticker>` — All filings (including extraction failures), extraction badges per section
- `/diff/<diff_id>` — Diff detail with sibling extraction statuses
- `/watchlist` — CRUD via watchlist.py module

## Key Spec Corrections

Original `REDLINE_SPEC.txt` issues fixed in build plan (`.claude/plans/polished-orbiting-pudding.md`):
- `difflib2` → stdlib `difflib`; `sec-api` → `edgartools` (free); `gpt-oss:20b` → `qwen2.5:13b-instruct` + `instructor`
- Legacy EDGAR CGI → `company_tickers.json`; `SEC_API_KEY` → `SEC_USER_AGENT`
- Added: `models.py`, `watchlist.py`, `extraction_attempts` table, `get_unprocessed_filings()`, `mark_filing_processed()`, `get_filings_for_ticker()`, `ExtractionResult` dataclass
- `get_cik()` returns `(cik, company_name, canonical_ticker)` — supports share-class tickers
- Backfill follows SEC `files` array for full 5-year history
- `pydantic` listed explicitly in requirements (not transitive via instructor)
