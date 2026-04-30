# RedLine

[![GitTok — vertical demo videos of finished GitHub projects](https://dev.gittok.net/og/readme-card.svg)](https://dev.gittok.net/feed)

**Automated SEC filing change detection and risk intelligence platform.** Monitors any publicly traded company on EDGAR, performs sentence-level diffing across 10-K/10-Q filings, flags material changes using pattern-based signal detection, scores and surfaces risk via local LLM analysis -- all running locally with zero paid API dependencies.

## What It Does

- **Universal coverage** -- track any SEC-reporting company by ticker; add one or a thousand
- **Deep extraction** -- pulls Risk Factors (1A), MD&A (7), Legal Proceedings (3), and Controls & Procedures (9A) from every filing
- **Two-mode sentence diffing** -- semantic diff via sentence embeddings (primary) with SequenceMatcher fallback
- **9 financial red flag detectors** -- going concern, restatement, covenant violation, auditor change, material weakness, goodwill impairment, revenue recognition change, related-party transactions, litigation risk
- **Two-stage scoring engine** -- fast deterministic score gates expensive LLM calls; only material changes get deep analysis
- **LLM analysis** -- local Ollama integration produces structured severity assessments with cited reasoning via `instructor` + Pydantic
- **Anomaly detection** -- embedding drift detection flags when a section deviates significantly from its historical mean (z-score threshold)
- **Trend analysis** -- tracks score trajectories and pct_changed volatility across filings with linear regression slope; requires 4+ periods per ticker/section
- **Real-time scheduler** -- market-hours polling (9:30-16:00 ET weekdays) every 5 minutes with high-score alert logging to JSONL
- **Crash-safe pipeline** -- interrupted runs resume automatically; idempotent writes prevent duplicates
- **5-year backfill** -- first run per ticker builds a full historical baseline including paginated SEC submission fragments
- **Web dashboard** -- dark-themed Flask UI with color-coded risk scores, per-company filing timelines, drill-down diff views, trends overview, and watchlist management

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env -- set SEC_USER_AGENT (required by EDGAR)

# Initialize database
python -c "from redline.data.storage import init_db; init_db()"

# Run the pipeline (backfills 5 years on first run)
python -m redline.pipeline

# Launch the web UI
python -m redline.web.app
# → http://localhost:5000

# Run the real-time polling scheduler (optional, market hours only)
python -m redline.scheduler
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Required | Default | Description |
|---|---|---|---|
| `SEC_USER_AGENT` | Yes | -- | `"YourName your@email.com"` (required by EDGAR) |
| `OLLAMA_HOST` | No | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | No | `qwen2.5:14b` | LLM model for analysis |
| `DB_PATH` | No | `./redline.db` | SQLite database path |
| `WATCHLIST_PATH` | No | `./watchlist.json` | Watchlist file path |
| `MIN_PCT_CHANGED` | No | `0.05` | Minimum change threshold to store diffs |
| `PRELIMINARY_SCORE_LLM_THRESHOLD` | No | `4` | Score threshold to trigger LLM analysis |
| `BACKFILL_YEARS` | No | `5` | Years of historical filings to fetch |
| `EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Sentence-transformer model for semantic diff |
| `SEMANTIC_DIFF_ENABLED` | No | `true` | Use semantic diff (falls back to SequenceMatcher) |
| `SEMANTIC_UNCHANGED_THRESHOLD` | No | `0.85` | Cosine similarity above which a sentence is "unchanged" |
| `SEMANTIC_CHANGED_THRESHOLD` | No | `0.55` | Cosine similarity below which a sentence is "added/deleted" |
| `STORE_EMBEDDINGS` | No | `true` | Persist section embeddings for anomaly detection |
| `ANOMALY_DETECTION_ENABLED` | No | `true` | Run embedding drift detection |
| `ANOMALY_MIN_HISTORY` | No | `3` | Minimum historical embeddings before anomaly detection fires |
| `ANOMALY_Z_THRESHOLD` | No | `2.0` | Z-score threshold for anomaly flag |
| `POLL_INTERVAL_SECONDS` | No | `300` | Polling interval for the real-time scheduler |
| `ALERT_SCORE_THRESHOLD` | No | `7` | Final score at or above which an alert is logged |

## Architecture

```
redline/
├── core/
│   ├── models.py          # Shared data contracts: FilingRecord, DiffResult, SignalResult, TrendResult
│   └── config.py          # All settings loaded from .env
├── ingestion/
│   ├── edgar.py           # SEC EDGAR API -- CIK resolution, filing fetch, pagination, rate limiting
│   └── extractor.py       # Section extraction from filing HTML (Item regex + HTML stripping)
├── analysis/
│   ├── differ.py          # Sentence-level diffing -- semantic (embeddings) with SequenceMatcher fallback
│   ├── semantic.py        # Embedding engine -- lazy-loads sentence-transformers, greedy bipartite matching
│   ├── signals.py         # 9 financial red flag pattern detectors (word-bounded regex)
│   ├── scorer.py          # preliminary_score() and final_score() -- sole scoring authority
│   ├── analyzer.py        # LLM analysis via Ollama + instructor (structured Pydantic output)
│   ├── anomaly.py         # Embedding drift detection -- cosine distance z-score against history
│   └── trends.py          # Score trajectory + pct_changed volatility (linear regression, 4+ periods)
├── data/
│   ├── storage.py         # SQLite access layer -- 7 tables, WAL mode, parameterized queries, migrations
│   └── watchlist.py       # Ticker watchlist management -- normalize, validate, atomic writes
├── pipeline.py            # Master orchestration -- backfill, poll, crash-resume
├── scheduler/
│   ├── polling.py         # Real-time EDGAR polling -- market hours logic, poll_once(), run_scheduler()
│   ├── alerts.py          # Alert logging to JSONL for high-score diffs
│   └── __main__.py        # Entry point: python -m redline.scheduler
├── web/
│   ├── app.py             # Flask UI -- dashboard, company, diff detail, trends, watchlist
│   ├── templates/         # Jinja2 templates (6 pages)
│   └── static/style.css   # Dark theme CSS
└── tests/                 # 172 tests across all modules
```

## Pipeline Flow

```
Watchlist → EDGAR Fetch → Section Extraction → Sentence Diff (semantic or legacy)
         → Signal Detection → Anomaly Detection → Preliminary Score
         → LLM Analysis (if score >= threshold) → Final Score
         → SQLite Storage → Trend Update → Web Dashboard / Alerts
```

- **Backfill mode**: triggered when `get_filing_count(cik, form_type) == 0` -- fetches up to 5 years including paginated SEC submission fragment files
- **Poll mode**: subsequent runs fetch only filings not yet in the database
- **Crash recovery**: filings with `processed=0` in the database are resumed before any new polling
- **Real-time mode**: the scheduler runs `poll_once()` every 5 minutes during market hours; diffs scoring at or above `ALERT_SCORE_THRESHOLD` are appended to `alerts/alerts.jsonl`

## Database Schema

7 tables managed by `data/storage.py` (SQLite, WAL mode):

| Table | Purpose |
|---|---|
| `companies` | CIK, ticker, company name |
| `filings` | Filing metadata -- form type, period, URL, processed flag |
| `sections` | Extracted plain text per filing + section |
| `diffs` | Diff results -- scores, signal flags, LLM output, semantic metadata |
| `extraction_attempts` | Status per filing/section (success/failed/not_found) |
| `section_embeddings` | Mean sentence embeddings per filing/section for anomaly detection |
| `trends` | Score trajectory and pct_changed volatility per ticker/form_type/section |

Schema migrations run idempotently on every startup via `_run_migrations()`.

## Signal Detection

| Signal | Severity | What It Catches |
|---|---|---|
| Going Concern | 9 | Doubts about ability to continue operating |
| Restatement | 8 | Corrections to previously reported financials |
| Debt Covenant Violation | 8 | Breaches, defaults, lender waivers |
| Auditor Change | 7 | Dismissed or resigned accountants |
| Material Weakness | 7 | Internal control deficiencies |
| Goodwill Impairment | 6 | Write-downs on acquisition value |
| Revenue Recognition Change | 5 | Accounting policy shifts |
| Related-Party Transaction | 5 | Insider dealings |
| Litigation Risk | 4 | Class actions, material legal proceedings |

All patterns use `\b` word boundaries, non-capturing groups for SEC wording variants, and bounded wildcards (`.{0,N}`) to prevent runaway matching.

## Scoring

**Preliminary score** (1-10): deterministic, fast.
- Base from `pct_changed` thresholds: `<5%->1`, `<15%->2`, `<30%->3`, `<50%->5`, `>=50%->6`
- Signal boost: `max_severity // 2` when any signals fired
- Going-concern override: any signal with severity >= 9 floors the score at 7
- Result clamped to `[1, 10]`

**Final score** (1-10): blends preliminary (40%) with LLM severity (60%) when LLM ran. If Ollama is unavailable or the preliminary score is below threshold, final score equals preliminary.

## Semantic Diff

The semantic differ (`analysis/semantic.py`) uses greedy bipartite matching on sentence embeddings:

1. Encode old and new sentences with `sentence-transformers` (default: `all-MiniLM-L6-v2`)
2. Build cosine similarity matrix between all pairs
3. Greedily match highest-similarity pairs first (each sentence matched at most once)
4. Classify matches: similarity >= `SEMANTIC_UNCHANGED_THRESHOLD` -> unchanged; between thresholds -> modified; unmatched -> added/deleted
5. Store per-filing mean embedding in `section_embeddings` for anomaly detection

Falls back to `difflib.SequenceMatcher` if `torch` is unavailable, imports fail, or `SEMANTIC_DIFF_ENABLED=false`. The fallback engages automatically -- no configuration needed.

## Anomaly Detection

After each section is processed, `analysis/anomaly.py` computes cosine distance from the historical mean embedding for that company + form_type + section. A z-score above `ANOMALY_Z_THRESHOLD` (default 2.0) flags the section as anomalous. Requires at least `ANOMALY_MIN_HISTORY` (default 3) historical embeddings; silently skips otherwise.

## Trend Analysis

`analysis/trends.py` computes per-(ticker, form_type, section) trend metrics after each filing is processed. Requires 4+ periods. Metrics include:
- `score_slope` -- linear regression slope over time (positive = worsening)
- `direction` -- `improving` / `stable` / `worsening` based on slope thresholds (+/-0.3)
- `volatile` -- True if pct_changed standard deviation > 0.10
- Full score and pct_changed time-series stored as JSON for the trends UI

## Commands

```bash
python -m redline.pipeline              # Run full pipeline (backfill + poll)
python -m redline.web.app               # Flask UI on localhost:5000
python -m redline.scheduler             # Real-time polling scheduler (market hours)
pytest redline/tests/                   # All 172 tests
pytest redline/tests/test_signals.py    # Single module
```

## Scheduling (Windows)

```powershell
# Create daily scheduled task (runs at 6 AM)
powershell -ExecutionPolicy Bypass -File scheduler\setup_task.ps1
```

The real-time scheduler (`python -m redline.scheduler`) is an alternative -- polls continuously during market hours (9:30-16:00 ET, weekdays) and sleeps until the next open otherwise.

## Watchlist

Ships with 20 default tickers across sectors -- tech, finance, pharma, energy, aerospace. Add any SEC-reporting ticker through the web UI at `/watchlist` or edit `watchlist.json` directly. Tickers like `BRK.B` are automatically normalized to SEC format (`BRK-B`). The watchlist file is written atomically (`tempfile` + `os.replace`) to prevent corruption.

## Tests

172 tests covering all modules. All external calls (EDGAR HTTP, Ollama) are mocked; no network access or Ollama instance required to run the suite.

```bash
pytest redline/tests/ -v
```

| Module | Tests | Coverage |
|---|---|---|
| `test_signals.py` | 40 | All 9 signal patterns, positive/negative/variant cases |
| `test_differ.py` | 23 | Legacy + semantic modes, sentence splitting, preview truncation |
| `test_semantic.py` | 18 | Similarity matrix, greedy matching, threshold classification |
| `test_scorer.py` | 19 | All scoring boundaries, going-concern override, clamping |
| `test_storage.py` | 15 | All 7 tables, WAL mode, idempotency, crash-recovery queries |
| `test_scheduler.py` | 16 | Market hours logic, alert logging, poll_once |
| `test_edgar.py` | 9 | CIK resolution, pagination, rate-limit retry |
| `test_pipeline.py` | 7 | Backfill, crash-resume, idempotency, oldest-first ordering |
| `test_analyzer.py` | 7 | Structured LLM output, error handling |
| `test_extractor.py` | 7 | Section extraction, HTML cleaning |
| `test_watchlist.py` | 11 | Add/remove, normalization, atomic writes |

## Tech Stack

- **Python 3.11+** -- uses `list[str]`, `dict | None`, `str | None` type hints throughout
- **SQLite** -- WAL mode, 7 tables, parameterized queries only, idempotent migrations
- **Flask** -- pure server-side HTML/CSS web UI (no JavaScript frameworks)
- **sentence-transformers + scikit-learn** -- local sentence embedding model for semantic diff and anomaly detection
- **Ollama + instructor + Pydantic** -- structured LLM output via local model (no cloud API)
- **requests + edgartools** -- EDGAR HTTP client with rate limiting and exponential backoff on 429s
- **pytest** -- 172 tests, all mocked, no network required
