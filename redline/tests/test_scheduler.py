"""Tests for redline.scheduler — polling scheduler and alert logging."""

import json
import os
import tempfile

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from redline.core import config
from redline.core.models import FilingRecord
from redline.data import storage
from redline.scheduler.alerts import log_alert
from redline.scheduler.polling import _is_market_hours, _seconds_until_market_open, poll_once


@pytest.fixture(autouse=True)
def tmp_env(monkeypatch):
    """Temp DB, watchlist, and alerts file for every test."""
    fd_db, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd_db)
    fd_wl, wl_path = tempfile.mkstemp(suffix=".json")
    os.close(fd_wl)
    tmp_dir = tempfile.mkdtemp()
    alerts_path = os.path.join(tmp_dir, "alerts.jsonl")

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "WATCHLIST_PATH", wl_path)
    monkeypatch.setattr(config, "ALERTS_PATH", alerts_path)
    with open(wl_path, "w") as f:
        json.dump({"tickers": ["AAPL"], "form_types": ["10-K"],
                    "sections": ["1A"]}, f)
    storage.init_db()
    yield db_path, wl_path, alerts_path
    for f in [db_path, db_path + "-wal", db_path + "-shm", wl_path]:
        if os.path.exists(f):
            os.unlink(f)
    if os.path.exists(alerts_path):
        os.unlink(alerts_path)
    if os.path.isdir(tmp_dir):
        os.rmdir(tmp_dir)


def _make_filing(**kw):
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


# --- _is_market_hours tests ---

class TestIsMarketHours:
    def test_weekday_during_hours(self):
        # Monday 10:00 ET
        dt = datetime(2026, 3, 23, 10, 0, 0)
        assert _is_market_hours(dt) is True

    def test_weekday_before_open(self):
        # Monday 9:00 ET
        dt = datetime(2026, 3, 23, 9, 0, 0)
        assert _is_market_hours(dt) is False

    def test_weekday_at_open(self):
        # Monday 9:30 ET
        dt = datetime(2026, 3, 23, 9, 30, 0)
        assert _is_market_hours(dt) is True

    def test_weekday_at_close(self):
        # Monday 16:00 ET — market close, should be False (< not <=)
        dt = datetime(2026, 3, 23, 16, 0, 0)
        assert _is_market_hours(dt) is False

    def test_weekday_just_before_close(self):
        dt = datetime(2026, 3, 23, 15, 59, 59)
        assert _is_market_hours(dt) is True

    def test_saturday(self):
        dt = datetime(2026, 3, 21, 12, 0, 0)  # Saturday
        assert _is_market_hours(dt) is False

    def test_sunday(self):
        dt = datetime(2026, 3, 22, 12, 0, 0)  # Sunday
        assert _is_market_hours(dt) is False


# --- _seconds_until_market_open tests ---

class TestSecondsUntilMarketOpen:
    def test_before_open_same_weekday(self):
        # Monday 8:30 → should be 1 hour (3600s) until 9:30
        dt = datetime(2026, 3, 23, 8, 30, 0)
        result = _seconds_until_market_open(dt)
        assert result == 3600.0

    def test_after_close_goes_to_next_day(self):
        # Monday 17:00 → next open is Tuesday 9:30 = 16.5 hours
        dt = datetime(2026, 3, 23, 17, 0, 0)
        result = _seconds_until_market_open(dt)
        assert result == 16.5 * 3600

    def test_friday_after_close_skips_weekend(self):
        # Friday 17:00 → next open is Monday 9:30 = 64.5 hours
        dt = datetime(2026, 3, 20, 17, 0, 0)
        result = _seconds_until_market_open(dt)
        assert result == 64.5 * 3600

    def test_saturday_skips_to_monday(self):
        # Saturday 12:00 → Monday 9:30 = 45.5 hours
        dt = datetime(2026, 3, 21, 12, 0, 0)
        result = _seconds_until_market_open(dt)
        assert result == 45.5 * 3600


# --- log_alert tests ---

class TestLogAlert:
    def test_writes_jsonl(self, tmp_env):
        _, _, alerts_path = tmp_env
        diff_dict = {
            "ticker": "AAPL",
            "filing_id": "000032019324000001",
            "form_type": "10-K",
            "period_of_report": "2024-09-28",
            "section": "1A",
            "preliminary_score": 8,
            "final_score": 9,
            "pct_changed": 0.45,
            "flags_json": '["going_concern"]',
        }
        log_alert(diff_dict)

        assert os.path.exists(alerts_path)
        with open(alerts_path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        alert = json.loads(lines[0])
        assert alert["ticker"] == "AAPL"
        assert alert["final_score"] == 9
        assert "timestamp" in alert

    def test_appends_multiple_alerts(self, tmp_env):
        _, _, alerts_path = tmp_env
        diff_dict = {
            "ticker": "AAPL", "filing_id": "id1", "form_type": "10-K",
            "period_of_report": "2024-09-28", "section": "1A",
            "preliminary_score": 7, "final_score": 8,
            "pct_changed": 0.3, "flags_json": "[]",
        }
        log_alert(diff_dict)
        log_alert(diff_dict)

        with open(alerts_path) as f:
            lines = f.readlines()
        assert len(lines) == 2


# --- poll_once tests ---

class TestPollOnce:
    @patch("redline.scheduler.polling.edgar")
    def test_poll_no_new_filings(self, mock_edgar, tmp_env):
        mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")
        mock_edgar.get_new_filings.return_value = []

        count = poll_once()
        assert count == 0

    @patch("redline.scheduler.polling._process_filing_with_alerts")
    @patch("redline.scheduler.polling.edgar")
    def test_poll_skips_existing_filing(self, mock_edgar, mock_process, tmp_env):
        filing = _make_filing()
        mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")
        mock_edgar.get_new_filings.return_value = [filing]

        # Pre-insert the filing so it's already known
        storage.upsert_company(filing.cik, filing.ticker, filing.company_name)
        storage.insert_filing(filing.filing_id, {
            "cik": filing.cik, "ticker": filing.ticker,
            "company_name": filing.company_name, "form_type": filing.form_type,
            "filed_at": filing.filed_at, "period_of_report": filing.period_of_report,
            "filing_url": filing.filing_url, "accession_number": filing.accession_number,
        })

        count = poll_once()
        assert count == 0
        mock_process.assert_not_called()

    @patch("redline.scheduler.polling._process_filing_with_alerts")
    @patch("redline.scheduler.polling.edgar")
    def test_poll_processes_new_filing(self, mock_edgar, mock_process, tmp_env):
        filing = _make_filing()
        mock_edgar.get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")
        mock_edgar.get_new_filings.return_value = [filing]

        count = poll_once()
        assert count == 1
        mock_process.assert_called_once()
