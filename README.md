# RedLine

**Automated SEC filing change detection and risk intelligence platform.** Monitors any publicly traded company on EDGAR, performs sentence-level diffing across 10-K and 10-Q filings, flags material changes using pattern-based signal detection, and surfaces risk insights through LLM-powered analysis — all running locally with zero paid API dependencies.

## What It Does

- **Universal coverage** — track any SEC-reporting company by ticker. Add one ticker or a thousand.
- **Deep extraction** — pulls Risk Factors (1A), MD&A (7), Legal Proceedings (3), and Controls & Procedures (9A) from every filing
- **Sentence-level diffing** — structural comparison between filing periods, not just word-level noise
- **9 financial red flag detectors** — going concern, restatement, covenant violation, auditor change, material weakness, goodwill impairment, revenue recognition changes, related-party transactions, litigation risk
- **Two-stage scoring engine** — fast deterministic scoring gates expensive LLM calls; only material changes get deep analysis
- **LLM analysis** — local Ollama integration produces structured severity assessments with cited reasoning
- **Crash-safe pipeline** — interrupted runs resume automatically; idempotent writes prevent duplicates
- **5-year backfill** — first run builds a full historical baseline per ticker, including paginated SEC submission fragments
- **Web dashboard** — color-coded risk scores, per-company filing timelines, drill-down diff views with extraction status

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env — set SEC_USER_AGENT (required by EDGAR)

# Initialize database
python -c "from redline.data.storage import init_db; init_db()"

# Run the pipeline (backfills 5 years on first run)
python -m redline.pipeline

# Launch the web UI
python -m redline.web.app
# → http://localhost:5000
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SEC_USER_AGENT` | Yes | — | `"YourName your@email.com"` (required by EDGAR) |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | No | `qwen2.5:14b` | LLM model for analysis |
| `DB_PATH` | No | `./redline.db` | SQLite database path |
| `WATCHLIST_PATH` | No | `./watchlist.json` | Watchlist file path |
| `MIN_PCT_CHANGED` | No | `0.05` | Minimum change threshold to store diffs |
| `PRELIMINARY_SCORE_LLM_THRESHOLD` | No | `4` | Score threshold to trigger LLM analysis |
| `BACKFILL_YEARS` | No | `5` | Years of historical filings to fetch |

## Architecture

```
redline/
├── core/
│   ├── models.py      # Shared data contracts (FilingRecord, DiffResult, SignalResult)
│   └── config.py      # All settings from .env
├── ingestion/
│   ├── edgar.py       # SEC EDGAR API (CIK resolution, filing fetch, pagination)
│   └── extractor.py   # Section extraction from filing HTML
├── analysis/
│   ├── differ.py      # Sentence-level structural diffing via difflib
│   ├── signals.py     # 9 financial red flag pattern detectors
│   ├── scorer.py      # Preliminary + LLM-weighted final scoring (1–10)
│   └── analyzer.py    # LLM analysis via Ollama with structured Pydantic output
├── data/
│   ├── storage.py     # SQLite (5 tables, WAL mode, parameterized queries)
│   └── watchlist.py   # Ticker watchlist management with atomic writes
├── pipeline.py        # Master orchestration (backfill, poll, crash-resume)
├── web/
│   ├── app.py         # Flask UI (dashboard, company, diff detail, watchlist)
│   ├── templates/     # Jinja2 templates
│   └── static/        # CSS (dark theme)
└── tests/             # 123 tests across all modules
```

## Pipeline Flow

```
Watchlist → EDGAR Fetch → Section Extraction → Sentence Diff
         → Signal Detection → Preliminary Score → LLM Analysis (if score ≥ 4)
         → Final Score → SQLite Storage → Web Dashboard
```

- **Backfill mode**: triggered automatically when a ticker has no prior filings — fetches up to 5 years of history including paginated SEC submission fragments
- **Poll mode**: subsequent runs fetch only new filings since last run
- **Crash recovery**: unprocessed filings (interrupted mid-run) are resumed before polling new data

## Signal Detection

| Signal | Severity | What It Catches |
|--------|----------|-----------------|
| Going Concern | 9 | Doubts about ability to continue operating |
| Restatement | 8 | Corrections to previously reported financials |
| Debt Covenant Violation | 8 | Breaches, defaults, lender waivers |
| Auditor Change | 7 | Dismissed/resigned accountants |
| Material Weakness | 7 | Internal control deficiencies |
| Goodwill Impairment | 6 | Write-downs on acquisition value |
| Revenue Recognition Change | 5 | Accounting policy shifts |
| Related-Party Transaction | 5 | Insider dealings |
| Litigation Risk | 4 | Class actions, material legal proceedings |

All patterns use word-bounded, case-insensitive regex with SEC-specific wording variants.

## Scoring

**Preliminary score** (1–10): deterministic, based on % changed + signal severity. Going concern language always scores 7+.

**Final score** (1–10): blends preliminary (40%) with LLM severity (60%) when available. LLM only runs when preliminary score meets threshold — keeps analysis fast and resource-efficient.

## Commands

```bash
python -m redline.pipeline              # Run full pipeline
python -m redline.web.app               # Flask UI on localhost:5000
pytest redline/tests/                   # All 123 tests
pytest redline/tests/test_signals.py    # Single module
```

## Scheduling (Windows)

```powershell
# Create daily scheduled task (runs at 6 AM)
powershell -ExecutionPolicy Bypass -File scheduler\setup_task.ps1
```

## Watchlist

Ships with 20 default tickers across sectors — tech, finance, pharma, energy, aerospace. Add any SEC-reporting ticker through the web UI at `/watchlist` or edit `watchlist.json` directly. Tickers like `BRK.B` are automatically normalized to SEC format (`BRK-B`).

## Tests

```bash
pytest redline/tests/ -v  # 123 tests covering all modules
```

Full coverage across ingestion, extraction, diffing, scoring, signals, storage, watchlist, LLM analysis, and end-to-end pipeline. All external calls (EDGAR HTTP, Ollama) are mocked.
