"""Tests for redline.storage — SQLite access layer."""

import os
import tempfile
import pytest

from redline.core import config
from redline.data import storage


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch):
    """Point config.DB_PATH at a temporary database for every test."""
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(config, "DB_PATH", db_file)
    storage.init_db()
    yield db_file
    for f in [db_file, db_file + "-wal", db_file + "-shm"]:
        if os.path.exists(f):
            os.unlink(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_company(cik="0000320193", ticker="AAPL", name="Apple Inc."):
    storage.upsert_company(cik, ticker, name)
    return cik, ticker, name


def _make_filing(
    filing_id="000032019324000001",
    cik="0000320193",
    ticker="AAPL",
    company_name="Apple Inc.",
    form_type="10-K",
    filed_at="2024-11-01T00:00:00+00:00",
    period_of_report="2024-09-28",
    filing_url="https://www.sec.gov/Archives/edgar/data/320193/filing.htm",
    accession_number="0000320193-24-000001",
):
    _make_company(cik, ticker, company_name)
    filing_dict = {
        "cik": cik,
        "ticker": ticker,
        "company_name": company_name,
        "form_type": form_type,
        "filed_at": filed_at,
        "period_of_report": period_of_report,
        "filing_url": filing_url,
        "accession_number": accession_number,
    }
    storage.insert_filing(filing_id, filing_dict)
    return filing_id, filing_dict


# ---------------------------------------------------------------------------
# 1. init_db creates all 5 tables
# ---------------------------------------------------------------------------

def test_init_db_creates_tables(tmp_db):
    import sqlite3

    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = sorted(r["name"] for r in rows)
    conn.close()

    expected = sorted([
        "companies", "filings", "sections", "diffs", "extraction_attempts",
        "section_embeddings",
    ])
    assert table_names == expected


# ---------------------------------------------------------------------------
# 2. WAL mode is set
# ---------------------------------------------------------------------------

def test_wal_mode(tmp_db):
    import sqlite3

    conn = sqlite3.connect(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


# ---------------------------------------------------------------------------
# 3. upsert_company is idempotent
# ---------------------------------------------------------------------------

def test_upsert_company_idempotent(tmp_db):
    import sqlite3

    storage.upsert_company("0000320193", "AAPL", "Apple Inc.")
    storage.upsert_company("0000320193", "AAPL", "Apple Inc. (updated)")

    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM companies WHERE cik = '0000320193'").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["name"] == "Apple Inc. (updated)"


# ---------------------------------------------------------------------------
# 4. filing_exists returns True/False correctly
# ---------------------------------------------------------------------------

def test_filing_exists():
    fid, _ = _make_filing()
    assert storage.filing_exists(fid) is True
    assert storage.filing_exists("nonexistent") is False


# ---------------------------------------------------------------------------
# 5. get_previous_filing returns correct filing
# ---------------------------------------------------------------------------

def test_get_previous_filing():
    cik, ticker, name = _make_company()

    # Insert two filings with different periods
    _make_filing(
        filing_id="000032019323000001",
        cik=cik,
        ticker=ticker,
        company_name=name,
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000001",
    )
    _make_filing(
        filing_id="000032019324000001",
        cik=cik,
        ticker=ticker,
        company_name=name,
        period_of_report="2024-09-28",
        accession_number="0000320193-24-000001",
    )

    # Should return the 2023 filing when looking before 2024-09-28
    prev = storage.get_previous_filing(cik, "10-K", "2024-09-28")
    assert prev is not None
    assert prev["id"] == "000032019323000001"
    assert prev["period_of_report"] == "2023-09-30"

    # Nothing before 2023
    prev2 = storage.get_previous_filing(cik, "10-K", "2023-01-01")
    assert prev2 is None


# ---------------------------------------------------------------------------
# 6. get_unprocessed_filings returns only processed=0
# ---------------------------------------------------------------------------

def test_get_unprocessed_filings():
    fid1, _ = _make_filing(
        filing_id="000032019323000001",
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000001",
    )
    fid2, _ = _make_filing(
        filing_id="000032019324000001",
        period_of_report="2024-09-28",
        accession_number="0000320193-24-000001",
    )

    # Mark one as processed
    storage.mark_filing_processed(fid1)

    unprocessed = storage.get_unprocessed_filings()
    ids = [f["id"] for f in unprocessed]
    assert fid2 in ids
    assert fid1 not in ids


# ---------------------------------------------------------------------------
# 7. mark_filing_processed flips the flag
# ---------------------------------------------------------------------------

def test_mark_filing_processed():
    fid, _ = _make_filing()

    # Initially unprocessed
    unprocessed = storage.get_unprocessed_filings()
    assert any(f["id"] == fid for f in unprocessed)

    storage.mark_filing_processed(fid)

    # Now should not appear in unprocessed
    unprocessed = storage.get_unprocessed_filings()
    assert not any(f["id"] == fid for f in unprocessed)


# ---------------------------------------------------------------------------
# 8. insert_section and get_section round-trip
# ---------------------------------------------------------------------------

def test_section_roundtrip():
    fid, _ = _make_filing()
    text = "This is the risk factors section with lots of detail."

    storage.insert_section(fid, "1A", text)

    result = storage.get_section(fid, "1A")
    assert result is not None
    assert result["filing_id"] == fid
    assert result["section"] == "1A"
    assert result["raw_text"] == text
    assert result["id"] is not None
    assert result["created_at"] is not None

    # Non-existent section returns None
    assert storage.get_section(fid, "7") is None


def test_section_upsert():
    """INSERT OR REPLACE should update the text if the same (filing_id, section) is inserted again."""
    fid, _ = _make_filing()

    storage.insert_section(fid, "1A", "old text")
    storage.insert_section(fid, "1A", "new text")

    result = storage.get_section(fid, "1A")
    assert result["raw_text"] == "new text"


# ---------------------------------------------------------------------------
# 9. insert_extraction_attempt and get_extraction_attempts round-trip
# ---------------------------------------------------------------------------

def test_extraction_attempt_roundtrip():
    fid, _ = _make_filing()

    storage.insert_extraction_attempt(fid, "1A", "success")
    storage.insert_extraction_attempt(fid, "7", "failed", error_msg="Parse error")
    storage.insert_extraction_attempt(fid, "9A", "not_found")

    attempts = storage.get_extraction_attempts(fid)
    assert len(attempts) == 3

    by_section = {a["section"]: a for a in attempts}
    assert by_section["1A"]["status"] == "success"
    assert by_section["1A"]["error_msg"] is None
    assert by_section["7"]["status"] == "failed"
    assert by_section["7"]["error_msg"] == "Parse error"
    assert by_section["9A"]["status"] == "not_found"


def test_extraction_attempt_upsert():
    """INSERT OR REPLACE should update status for the same (filing_id, section)."""
    fid, _ = _make_filing()

    storage.insert_extraction_attempt(fid, "1A", "failed", error_msg="Timeout")
    storage.insert_extraction_attempt(fid, "1A", "success")

    attempts = storage.get_extraction_attempts(fid)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "success"
    assert attempts[0]["error_msg"] is None


# ---------------------------------------------------------------------------
# 10. get_filings_for_ticker returns correct results
# ---------------------------------------------------------------------------

def test_get_filings_for_ticker():
    # Create filings for two tickers
    _make_filing(
        filing_id="000032019324000001",
        cik="0000320193",
        ticker="AAPL",
        company_name="Apple Inc.",
        period_of_report="2024-09-28",
        accession_number="0000320193-24-000001",
    )
    _make_filing(
        filing_id="000032019323000001",
        cik="0000320193",
        ticker="AAPL",
        company_name="Apple Inc.",
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000001",
    )
    _make_company("0000789019", "MSFT", "Microsoft Corporation")
    _make_filing(
        filing_id="000078901924000001",
        cik="0000789019",
        ticker="MSFT",
        company_name="Microsoft Corporation",
        period_of_report="2024-06-30",
        accession_number="0000789019-24-000001",
    )

    aapl_filings = storage.get_filings_for_ticker("AAPL")
    assert len(aapl_filings) == 2
    # Should be ordered by period_of_report DESC
    assert aapl_filings[0]["period_of_report"] == "2024-09-28"
    assert aapl_filings[1]["period_of_report"] == "2023-09-30"

    msft_filings = storage.get_filings_for_ticker("MSFT")
    assert len(msft_filings) == 1
    assert msft_filings[0]["ticker"] == "MSFT"

    # Non-existent ticker
    none_filings = storage.get_filings_for_ticker("GOOG")
    assert len(none_filings) == 0


# ---------------------------------------------------------------------------
# Bonus: diff insert / get / update
# ---------------------------------------------------------------------------

def test_diff_roundtrip():
    """Insert, get, and update a diff."""
    fid1, _ = _make_filing(
        filing_id="000032019323000001",
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000001",
    )
    fid2, _ = _make_filing(
        filing_id="000032019324000001",
        period_of_report="2024-09-28",
        accession_number="0000320193-24-000001",
    )

    diff_dict = {
        "filing_id": fid2,
        "prev_filing_id": fid1,
        "section": "1A",
        "ticker": "AAPL",
        "form_type": "10-K",
        "period_of_report": "2024-09-28",
        "pct_changed": 0.35,
        "word_count_old": 5000,
        "word_count_new": 5200,
        "word_count_delta": 200,
        "sentences_added": 10,
        "sentences_removed": 5,
        "sentences_unchanged": 100,
        "diff_preview": "some preview text",
        "preliminary_score": 5,
        "flags_json": '[{"flag": "revenue_decline"}]',
    }

    storage.insert_diff(diff_dict)

    all_diffs = storage.get_all_diffs()
    assert len(all_diffs) == 1
    d = all_diffs[0]
    assert d["filing_id"] == fid2
    assert d["pct_changed"] == 0.35
    assert d["preliminary_score"] == 5
    assert d["final_score"] is None

    # Update with LLM results
    storage.update_diff_llm(d["id"], final_score=7, llm_output="LLM says risky")
    updated = storage.get_diff_by_id(d["id"])
    assert updated["final_score"] == 7
    assert updated["llm_output"] == "LLM says risky"


def test_get_diffs_for_ticker():
    fid1, _ = _make_filing(
        filing_id="000032019323000001",
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000001",
    )
    fid2, _ = _make_filing(
        filing_id="000032019324000001",
        period_of_report="2024-09-28",
        accession_number="0000320193-24-000001",
    )

    diff_dict = {
        "filing_id": fid2,
        "prev_filing_id": fid1,
        "section": "1A",
        "ticker": "AAPL",
        "form_type": "10-K",
        "period_of_report": "2024-09-28",
        "pct_changed": 0.2,
        "word_count_old": 1000,
        "word_count_new": 1100,
        "word_count_delta": 100,
        "sentences_added": 3,
        "sentences_removed": 1,
        "sentences_unchanged": 50,
        "preliminary_score": 3,
    }
    storage.insert_diff(diff_dict)

    diffs = storage.get_diffs_for_ticker("AAPL")
    assert len(diffs) == 1
    assert diffs[0]["ticker"] == "AAPL"

    diffs_none = storage.get_diffs_for_ticker("MSFT")
    assert len(diffs_none) == 0


def test_get_filing_count():
    _make_filing(
        filing_id="000032019323000001",
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000001",
        form_type="10-K",
    )
    _make_filing(
        filing_id="000032019324000001",
        period_of_report="2024-09-28",
        accession_number="0000320193-24-000001",
        form_type="10-K",
    )
    _make_filing(
        filing_id="000032019324000002",
        period_of_report="2024-03-31",
        accession_number="0000320193-24-000002",
        form_type="10-Q",
    )

    assert storage.get_filing_count("0000320193", "10-K") == 2
    assert storage.get_filing_count("0000320193", "10-Q") == 1
    assert storage.get_filing_count("0000320193", "8-K") == 0
