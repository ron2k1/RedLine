"""Sole SQLite access layer for Redline.

Uses WAL mode. 5 tables: companies, filings, sections, diffs, extraction_attempts.
All APIs use filing_id (accession number with dashes removed) as the canonical key.
"""

import sqlite3
import uuid
from datetime import datetime, timezone

from redline.core import config


def _connect() -> sqlite3.Connection:
    """Return connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all 5 tables if they don't exist. Set WAL mode."""
    conn = _connect()
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            cik         TEXT PRIMARY KEY,
            ticker      TEXT NOT NULL,
            name        TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS filings (
            id              TEXT PRIMARY KEY,
            cik             TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            company_name    TEXT NOT NULL,
            form_type       TEXT NOT NULL,
            filed_at        TEXT NOT NULL,
            period_of_report TEXT NOT NULL,
            filing_url      TEXT NOT NULL,
            accession_number TEXT NOT NULL,
            processed       INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (cik) REFERENCES companies(cik)
        );

        CREATE TABLE IF NOT EXISTS sections (
            id          TEXT PRIMARY KEY,
            filing_id   TEXT NOT NULL,
            section     TEXT NOT NULL,
            raw_text    TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (filing_id) REFERENCES filings(id),
            UNIQUE(filing_id, section)
        );

        CREATE TABLE IF NOT EXISTS diffs (
            id              TEXT PRIMARY KEY,
            filing_id       TEXT NOT NULL,
            prev_filing_id  TEXT NOT NULL,
            section         TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            form_type       TEXT NOT NULL,
            period_of_report TEXT NOT NULL,
            pct_changed     REAL NOT NULL,
            word_count_old  INTEGER NOT NULL,
            word_count_new  INTEGER NOT NULL,
            word_count_delta INTEGER NOT NULL,
            sentences_added INTEGER NOT NULL,
            sentences_removed INTEGER NOT NULL,
            sentences_unchanged INTEGER NOT NULL,
            diff_preview    TEXT,
            preliminary_score INTEGER NOT NULL,
            final_score     INTEGER,
            flags_json      TEXT,
            llm_output      TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (filing_id) REFERENCES filings(id),
            FOREIGN KEY (prev_filing_id) REFERENCES filings(id),
            UNIQUE(filing_id, prev_filing_id, section)
        );

        CREATE TABLE IF NOT EXISTS extraction_attempts (
            id          TEXT PRIMARY KEY,
            filing_id   TEXT NOT NULL,
            section     TEXT NOT NULL,
            status      TEXT NOT NULL,
            error_msg   TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (filing_id) REFERENCES filings(id),
            UNIQUE(filing_id, section)
        );
    """)

    conn.commit()
    conn.close()


def _now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def upsert_company(cik: str, ticker: str, name: str):
    """INSERT OR REPLACE into companies."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO companies (cik, ticker, name, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (cik, ticker, name, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def insert_filing(filing_id: str, filing_dict: dict):
    """Insert a new filing with processed=0.

    filing_dict has keys matching FilingRecord fields.
    """
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO filings "
            "(id, cik, ticker, company_name, form_type, filed_at, "
            "period_of_report, filing_url, accession_number, processed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (
                filing_id,
                filing_dict["cik"],
                filing_dict["ticker"],
                filing_dict["company_name"],
                filing_dict["form_type"],
                filing_dict["filed_at"],
                filing_dict["period_of_report"],
                filing_dict["filing_url"],
                filing_dict["accession_number"],
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def filing_exists(filing_id: str) -> bool:
    """Check if filing_id exists in filings table."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM filings WHERE id = ?", (filing_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_filing_count(cik: str, form_type: str) -> int:
    """Count filings for a given cik and form_type."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM filings WHERE cik = ? AND form_type = ?",
            (cik, form_type),
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def get_previous_filing(cik: str, form_type: str, before_period: str) -> dict | None:
    """Get the most recent filing for cik+form_type with period_of_report < before_period.

    Returns dict with filing columns or None.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM filings "
            "WHERE cik = ? AND form_type = ? AND period_of_report < ? "
            "ORDER BY period_of_report DESC LIMIT 1",
            (cik, form_type, before_period),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_unprocessed_filings() -> list[dict]:
    """SELECT * FROM filings WHERE processed = 0 ORDER BY period_of_report ASC."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM filings WHERE processed = 0 "
            "ORDER BY period_of_report ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_filings_for_ticker(ticker: str) -> list[dict]:
    """All filings for a ticker, ordered by period_of_report DESC."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM filings WHERE ticker = ? "
            "ORDER BY period_of_report DESC",
            (ticker,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_section(filing_id: str, section: str, raw_text: str):
    """Insert section text. Uses uuid4 for id. UNIQUE(filing_id, section) with INSERT OR REPLACE."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sections (id, filing_id, section, raw_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), filing_id, section, raw_text, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_section(filing_id: str, section: str) -> dict | None:
    """Get section by filing_id and section code."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM sections WHERE filing_id = ? AND section = ?",
            (filing_id, section),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_extraction_attempt(
    filing_id: str, section: str, status: str, error_msg: str = None
):
    """Insert extraction attempt. Uses uuid4 for id. UNIQUE(filing_id, section) with INSERT OR REPLACE."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO extraction_attempts "
            "(id, filing_id, section, status, error_msg, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), filing_id, section, status, error_msg, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_extraction_attempts(filing_id: str) -> list[dict]:
    """Get all extraction attempts for a filing."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM extraction_attempts WHERE filing_id = ?",
            (filing_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_diff(diff_dict: dict):
    """Insert a diff record. Uses uuid4 for id if not provided.

    UNIQUE(filing_id, prev_filing_id, section) prevents duplicates on
    crash-retry — INSERT OR REPLACE safely overwrites a prior partial row.
    """
    diff_id = diff_dict.get("id", str(uuid.uuid4()))
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO diffs "
            "(id, filing_id, prev_filing_id, section, ticker, form_type, "
            "period_of_report, pct_changed, word_count_old, word_count_new, "
            "word_count_delta, sentences_added, sentences_removed, "
            "sentences_unchanged, diff_preview, preliminary_score, "
            "final_score, flags_json, llm_output, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                diff_id,
                diff_dict["filing_id"],
                diff_dict["prev_filing_id"],
                diff_dict["section"],
                diff_dict["ticker"],
                diff_dict["form_type"],
                diff_dict["period_of_report"],
                diff_dict["pct_changed"],
                diff_dict["word_count_old"],
                diff_dict["word_count_new"],
                diff_dict["word_count_delta"],
                diff_dict["sentences_added"],
                diff_dict["sentences_removed"],
                diff_dict["sentences_unchanged"],
                diff_dict.get("diff_preview"),
                diff_dict["preliminary_score"],
                diff_dict.get("final_score"),
                diff_dict.get("flags_json"),
                diff_dict.get("llm_output"),
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_diff_llm(diff_id: str, final_score: int, llm_output: str):
    """Update a diff with LLM results."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE diffs SET final_score = ?, llm_output = ? WHERE id = ?",
            (final_score, llm_output, diff_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_filing_processed(filing_id: str):
    """UPDATE filings SET processed = 1 WHERE id = ?"""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE filings SET processed = 1 WHERE id = ?", (filing_id,)
        )
        conn.commit()
    finally:
        conn.close()


def get_all_diffs(limit: int = 50) -> list[dict]:
    """Get most recent diffs, ordered by created_at DESC."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM diffs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_diffs_for_ticker(ticker: str) -> list[dict]:
    """Get all diffs for a ticker, ordered by created_at DESC."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM diffs WHERE ticker = ? ORDER BY created_at DESC",
            (ticker,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_diff_by_id(diff_id: str) -> dict | None:
    """Get a single diff by its id."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM diffs WHERE id = ?", (diff_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
