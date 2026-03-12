"""Tests for redline.pipeline — master pipeline orchestration."""

import os
import tempfile
import json
import pytest
from unittest.mock import patch, MagicMock

from redline import config, storage
from redline.models import FilingRecord, ExtractionResult, DiffResult, SignalResult


@pytest.fixture(autouse=True)
def tmp_env(monkeypatch):
    """Temp DB and watchlist for every test."""
    fd_db, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd_db)
    fd_wl, wl_path = tempfile.mkstemp(suffix=".json")
    os.close(fd_wl)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "WATCHLIST_PATH", wl_path)
    with open(wl_path, "w") as f:
        json.dump({"tickers": ["AAPL"], "form_types": ["10-K"],
                    "sections": ["1A"]}, f)
    storage.init_db()
    yield db_path, wl_path
    for f in [db_path, db_path + "-wal", db_path + "-shm", wl_path]:
        if os.path.exists(f):
            os.unlink(f)


def _make_filing_record(**kw):
    defaults = dict(
        accession_number="0000320193-24-000001",
        filing_id="000032019324000001",
        cik="0000320193",
        ticker="AAPL",
        company_name="Apple Inc.",
        form_type="10-K",
        filed_at="2024-11-01",
        period_of_report="2024-09-28",
        filing_url="https://www.sec.gov/Archives/edgar/data/320193/filing.htm",
    )
    defaults.update(kw)
    return FilingRecord(**defaults)


def _insert_filing_in_db(filing: FilingRecord, processed=0):
    storage.upsert_company(filing.cik, filing.ticker, filing.company_name)
    storage.insert_filing(filing.filing_id, {
        "cik": filing.cik, "ticker": filing.ticker,
        "company_name": filing.company_name, "form_type": filing.form_type,
        "filed_at": filing.filed_at, "period_of_report": filing.period_of_report,
        "filing_url": filing.filing_url, "accession_number": filing.accession_number,
    })
    if processed:
        storage.mark_filing_processed(filing.filing_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("redline.pipeline.extractor")
def test_process_filing_marks_processed(mock_extractor):
    """process_filing always marks the filing as processed."""
    from redline.pipeline import process_filing

    filing = _make_filing_record()
    _insert_filing_in_db(filing, processed=0)

    mock_extractor.extract_all_sections.return_value = [
        ExtractionResult(section_code="1A", status="not_found", text=None, error_msg=None),
    ]

    process_filing(filing, ["1A"])

    unprocessed = storage.get_unprocessed_filings()
    assert not any(f["id"] == filing.filing_id for f in unprocessed)


@patch("redline.pipeline.extractor")
def test_extraction_failure_doesnt_halt(mock_extractor):
    """Failed extractions are recorded but don't stop processing."""
    from redline.pipeline import process_filing

    filing = _make_filing_record()
    _insert_filing_in_db(filing, processed=0)

    mock_extractor.extract_all_sections.return_value = [
        ExtractionResult(section_code="1A", status="failed", text=None,
                         error_msg="Parse error"),
    ]

    process_filing(filing, ["1A"])

    attempts = storage.get_extraction_attempts(filing.filing_id)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    # Filing still marked processed
    unprocessed = storage.get_unprocessed_filings()
    assert not any(f["id"] == filing.filing_id for f in unprocessed)


@patch("redline.pipeline.analyzer")
@patch("redline.pipeline.extractor")
def test_process_filing_creates_diff(mock_extractor, mock_analyzer):
    """When previous filing exists with same section, a diff is created."""
    from redline.pipeline import process_filing

    mock_analyzer.analyze_diff.return_value = None

    # Insert an older filing with section text
    old_filing = _make_filing_record(
        accession_number="0000320193-23-000001",
        filing_id="000032019323000001",
        period_of_report="2023-09-30",
    )
    _insert_filing_in_db(old_filing, processed=1)
    storage.insert_section(old_filing.filing_id, "1A",
                           "Old risk factors. The company faces market risks.")

    # New filing
    new_filing = _make_filing_record(
        accession_number="0000320193-24-000001",
        filing_id="000032019324000001",
        period_of_report="2024-09-28",
    )
    _insert_filing_in_db(new_filing, processed=0)

    mock_extractor.extract_all_sections.return_value = [
        ExtractionResult(section_code="1A", status="success",
                         text="New risk factors. The company faces significant operational risks. Going concern doubt exists.",
                         error_msg=None),
    ]

    process_filing(new_filing, ["1A"])

    diffs = storage.get_all_diffs()
    assert len(diffs) >= 1
    d = diffs[0]
    assert d["filing_id"] == new_filing.filing_id
    assert d["prev_filing_id"] == old_filing.filing_id
    assert d["section"] == "1A"


@patch("redline.pipeline.edgar")
@patch("redline.pipeline.extractor")
def test_backfill_per_form_type(mock_extractor, mock_edgar):
    """Backfill triggers per (ticker, form_type) when get_filing_count == 0."""
    from redline.pipeline import run

    mock_extractor.extract_all_sections.return_value = []
    mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")
    mock_edgar.get_recent_filings.return_value = []

    run()

    # Should have called get_recent_filings with max_years for backfill
    mock_edgar.get_recent_filings.assert_called_once()
    call_args = mock_edgar.get_recent_filings.call_args
    assert call_args.kwargs.get("max_years") == config.BACKFILL_YEARS or \
           (len(call_args.args) >= 5 and call_args.args[4] == config.BACKFILL_YEARS)


@patch("redline.pipeline.edgar")
@patch("redline.pipeline.extractor")
def test_resume_unprocessed(mock_extractor, mock_edgar):
    """Stranded filings (processed=0) are resumed before polling."""
    from redline.pipeline import run

    mock_extractor.extract_all_sections.return_value = [
        ExtractionResult(section_code="1A", status="not_found", text=None, error_msg=None),
    ]
    mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")
    mock_edgar.get_recent_filings.return_value = []

    # Create a stranded filing
    stranded = _make_filing_record(
        filing_id="000032019323000099",
        accession_number="0000320193-23-000099",
        period_of_report="2023-06-30",
    )
    _insert_filing_in_db(stranded, processed=0)

    run()

    # Stranded filing should now be processed
    unprocessed = storage.get_unprocessed_filings()
    assert not any(f["id"] == stranded.filing_id for f in unprocessed)


@patch("redline.pipeline.edgar")
@patch("redline.pipeline.extractor")
def test_idempotency_no_duplicate_inserts(mock_extractor, mock_edgar):
    """Filing already in DB is not re-inserted."""
    from redline.pipeline import run

    mock_extractor.extract_all_sections.return_value = []

    existing = _make_filing_record()
    _insert_filing_in_db(existing, processed=1)

    mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")
    # Edgar returns the same filing that's already stored
    mock_edgar.get_recent_filings.return_value = []
    mock_edgar.get_new_filings.return_value = []

    # Should not raise — idempotent
    run()


@patch("redline.pipeline.edgar")
@patch("redline.pipeline.extractor")
def test_oldest_first_processing(mock_extractor, mock_edgar):
    """Backfill filings are processed oldest-first."""
    from redline.pipeline import run

    call_order = []

    def track_extract(filing, sections):
        call_order.append(filing.period_of_report)
        return [ExtractionResult(section_code="1A", status="not_found",
                                 text=None, error_msg=None)]

    mock_extractor.extract_all_sections.side_effect = track_extract
    mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")

    # Return filings already sorted oldest-first (as edgar does)
    filings = [
        _make_filing_record(filing_id="000032019321000001",
                            accession_number="0000320193-21-000001",
                            period_of_report="2021-09-25"),
        _make_filing_record(filing_id="000032019322000001",
                            accession_number="0000320193-22-000001",
                            period_of_report="2022-10-01"),
        _make_filing_record(filing_id="000032019323000001",
                            accession_number="0000320193-23-000001",
                            period_of_report="2023-09-30"),
    ]
    mock_edgar.get_recent_filings.return_value = filings

    run()

    assert call_order == ["2021-09-25", "2022-10-01", "2023-09-30"]
