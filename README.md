# RedLine

Local SEC filing change detection tool for Windows. Polls EDGAR for 10-K/10-Q filings, extracts key sections, diffs at sentence level, detects financial red flag patterns, runs LLM analysis via Ollama, stores in SQLite, displays via Flask. Everything runs locally — no cloud, no auth, no paid APIs.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env — set SEC_USER_AGENT (required by EDGAR)

# Initialize database
python -c "from redline.storage import init_db; init_db()"

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
| `OLLAMA_MODEL` | No | `qwen2.5:13b-instruct` | LLM model for analysis |
| `DB_PATH` | No | `./redline.db` | SQLite database path |
| `WATCHLIST_PATH` | No | `./watchlist.json` | Watchlist file path |

## Architecture

```
redline/
├── models.py      # Shared data contracts (FilingRecord, DiffResult, etc.)
├── config.py      # All settings from .env
├── edgar.py       # SEC EDGAR API (CIK resolution, filing fetch, pagination)
├── extractor.py   # Section extraction from filing HTML
├── differ.py      # Sentence-level diffing via difflib
├── signals.py     # 9 financial red flag pattern detectors
├── scorer.py      # Preliminary + LLM-weighted final scoring
├── analyzer.py    # LLM analysis via Ollama/instructor
├── storage.py     # SQLite (5 tables, WAL mode)
├── watchlist.py   # Ticker watchlist management
├── pipeline.py    # Master orchestration (backfill, poll, resume)
├── web/
│   ├── app.py     # Flask UI (dashboard, company, diff detail, watchlist)
│   ├── templates/ # Jinja2 templates
│   └── static/    # CSS
└── tests/         # 104 tests
```

## Commands

```bash
python -m redline.pipeline              # Run full pipeline
python -m redline.web.app               # Flask UI on localhost:5000
pytest redline/tests/                   # All tests
pytest redline/tests/test_differ.py     # Single test file
```

## Scheduling (Windows)

```powershell
# Create daily scheduled task (runs at 6 AM)
powershell -ExecutionPolicy Bypass -File scheduler\setup_task.ps1
```

## Watchlist

Default: `AAPL`, `TSLA`, `NVDA` tracking `10-K` and `10-Q` filings.

Manage via the web UI at `/watchlist`, or edit `watchlist.json` directly. Tickers like `BRK.B` are normalized to SEC format (`BRK-B`).

## Tests

```bash
pytest redline/tests/ -v  # 104 tests covering all modules
```
