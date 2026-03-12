"""Tests for redline.edgar — SEC EDGAR poller module.

All HTTP calls are mocked; no real EDGAR requests are made.
"""

from unittest.mock import patch, MagicMock, call
import pytest

from redline.models import FilingRecord


# ---------------------------------------------------------------------------
# Shared mock data fixtures
# ---------------------------------------------------------------------------

MOCK_COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1418091, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
    "2": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
}


def _make_submissions_response(
    accession_numbers=None,
    forms=None,
    filing_dates=None,
    report_dates=None,
    primary_documents=None,
    files=None,
):
    """Build a realistic CIK submissions JSON response."""
    if accession_numbers is None:
        accession_numbers = ["0000320193-24-000010", "0000320193-23-000090"]
        forms = ["10-K", "10-Q"]
        filing_dates = ["2024-11-01", "2023-08-04"]
        report_dates = ["2024-09-28", "2023-07-01"]
        primary_documents = ["aapl-20240928.htm", "aapl-20230701.htm"]

    return {
        "cik": "320193",
        "filings": {
            "recent": {
                "accessionNumber": accession_numbers,
                "form": forms,
                "filingDate": filing_dates,
                "reportDate": report_dates,
                "primaryDocument": primary_documents,
            },
            "files": files or [],
        },
    }


def _mock_response(json_data=None, status_code=200):
    """Create a mock requests.Response."""
    resp = MagicMock(spec=["json", "status_code", "raise_for_status"])
    resp.json.return_value = json_data
    resp.status_code = status_code
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetCik:
    """Tests for get_cik()."""

    @patch("redline.edgar._get")
    def test_returns_3_tuple(self, mock_get):
        """get_cik returns (cik_padded, company_name, canonical_ticker)."""
        mock_get.return_value = _mock_response(MOCK_COMPANY_TICKERS)

        from redline.edgar import get_cik

        result = get_cik("AAPL")
        assert result is not None
        cik, name, ticker = result
        assert cik == "0000320193"
        assert name == "Apple Inc."
        assert ticker == "AAPL"

    @patch("redline.edgar._get")
    def test_normalizes_dot_to_dash(self, mock_get):
        """get_cik normalizes BRK.B to BRK-B for lookup."""
        mock_get.return_value = _mock_response(MOCK_COMPANY_TICKERS)

        from redline.edgar import get_cik

        result = get_cik("BRK.B")
        assert result is not None
        cik, name, ticker = result
        assert cik == "0001418091"
        assert name == "BERKSHIRE HATHAWAY INC"
        assert ticker == "BRK-B"

    @patch("redline.edgar._get")
    def test_returns_none_for_unknown(self, mock_get):
        """get_cik returns None for unknown ticker."""
        mock_get.return_value = _mock_response(MOCK_COMPANY_TICKERS)

        from redline.edgar import get_cik

        result = get_cik("ZZZZZ")
        assert result is None


class TestGetFunction:
    """Tests for _get() HTTP helper."""

    @patch("redline.edgar.time")
    @patch("redline.edgar.requests.get")
    def test_sends_user_agent(self, mock_requests_get, mock_time):
        """_get sends the correct User-Agent header."""
        mock_time.time.return_value = 999.0  # bypass rate limiting
        mock_resp = _mock_response({"data": 1})
        mock_requests_get.return_value = mock_resp

        from redline.edgar import _get

        _get("https://example.com/test")

        mock_requests_get.assert_called_once()
        call_kwargs = mock_requests_get.call_args
        headers = call_kwargs[1].get("headers") or call_kwargs.kwargs.get("headers")
        assert "User-Agent" in headers

    @patch("redline.edgar.time")
    @patch("redline.edgar.requests.get")
    def test_retries_on_429(self, mock_requests_get, mock_time):
        """_get retries with exponential backoff on 429 responses."""
        mock_time.time.return_value = 999.0  # bypass rate limiting

        resp_429 = MagicMock()
        resp_429.status_code = 429

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.raise_for_status = MagicMock()

        mock_requests_get.side_effect = [resp_429, resp_ok]

        from redline.edgar import _get

        result = _get("https://example.com/test", max_retries=3)
        assert result.status_code == 200
        assert mock_requests_get.call_count == 2
        # Verify sleep was called for backoff (2^0 = 1 second)
        mock_time.sleep.assert_any_call(1)


class TestGetRecentFilings:
    """Tests for get_recent_filings()."""

    @patch("redline.edgar._get")
    def test_follows_files_array_for_pagination(self, mock_get):
        """get_recent_filings follows files array to get older filings."""
        main_response = _make_submissions_response(
            accession_numbers=["0000320193-24-000010"],
            forms=["10-K"],
            filing_dates=["2024-11-01"],
            report_dates=["2024-09-28"],
            primary_documents=["aapl-20240928.htm"],
            files=[{"name": "CIK0000320193-submissions-001.json"}],
        )

        fragment_response = {
            "accessionNumber": ["0000320193-21-000060"],
            "form": ["10-K"],
            "filingDate": ["2021-10-29"],
            "reportDate": ["2021-09-25"],
            "primaryDocument": ["aapl-20210925.htm"],
        }

        mock_get.side_effect = [
            _mock_response(main_response),
            _mock_response(fragment_response),
        ]

        from redline.edgar import get_recent_filings

        results = get_recent_filings(
            cik="0000320193",
            form_types=["10-K"],
            ticker="AAPL",
            company_name="Apple Inc.",
            max_years=5,
        )

        # Should have fetched the fragment file
        assert mock_get.call_count == 2
        assert any("submissions-001" in str(c) for c in mock_get.call_args_list)

        # Should have both filings
        assert len(results) == 2

    @patch("redline.edgar._get")
    def test_filters_by_max_years(self, mock_get):
        """get_recent_filings filters out filings older than max_years."""
        # One filing from 2025-12-28 (within 1 year of 2026-03-12),
        # one from 2019-09-28 (well outside 1 year)
        main_response = _make_submissions_response(
            accession_numbers=["0000320193-26-000010", "0000320193-19-000005"],
            forms=["10-K", "10-K"],
            filing_dates=["2026-01-15", "2019-10-30"],
            report_dates=["2025-12-28", "2019-09-28"],
            primary_documents=["aapl-20251228.htm", "aapl-20190928.htm"],
        )

        mock_get.return_value = _mock_response(main_response)

        from redline.edgar import get_recent_filings

        results = get_recent_filings(
            cik="0000320193",
            form_types=["10-K"],
            ticker="AAPL",
            company_name="Apple Inc.",
            max_years=1,
        )

        # Only the 2025-12-28 filing should remain
        assert len(results) == 1
        assert results[0].period_of_report == "2025-12-28"

    @patch("redline.edgar._get")
    def test_returns_filing_records_sorted_oldest_first(self, mock_get):
        """get_recent_filings returns FilingRecord objects sorted oldest first."""
        main_response = _make_submissions_response(
            accession_numbers=[
                "0000320193-24-000010",
                "0000320193-23-000090",
                "0000320193-22-000080",
            ],
            forms=["10-K", "10-K", "10-K"],
            filing_dates=["2024-11-01", "2023-10-27", "2022-10-28"],
            report_dates=["2024-09-28", "2023-09-30", "2022-10-01"],
            primary_documents=[
                "aapl-20240928.htm",
                "aapl-20230930.htm",
                "aapl-20221001.htm",
            ],
        )

        mock_get.return_value = _mock_response(main_response)

        from redline.edgar import get_recent_filings

        results = get_recent_filings(
            cik="0000320193",
            form_types=["10-K"],
            ticker="AAPL",
            company_name="Apple Inc.",
        )

        assert len(results) == 3
        # All are FilingRecord instances
        for r in results:
            assert isinstance(r, FilingRecord)

        # Sorted oldest first
        dates = [r.period_of_report for r in results]
        assert dates == sorted(dates)
        assert dates[0] == "2022-10-01"
        assert dates[-1] == "2024-09-28"

        # Verify FilingRecord fields
        rec = results[-1]  # the 2024 one
        assert rec.accession_number == "0000320193-24-000010"
        assert rec.filing_id == "000032019324000010"
        assert rec.cik == "0000320193"
        assert rec.ticker == "AAPL"
        assert rec.company_name == "Apple Inc."
        assert rec.form_type == "10-K"
        assert rec.filed_at == "2024-11-01"
        assert rec.period_of_report == "2024-09-28"
        assert "320193" in rec.filing_url
        assert "aapl-20240928.htm" in rec.filing_url


class TestGetNewFilings:
    """Tests for get_new_filings()."""

    @patch("redline.edgar.get_recent_filings")
    @patch("redline.edgar.get_cik")
    def test_filters_out_existing_filings(self, mock_get_cik, mock_get_recent):
        """get_new_filings filters out filings that already exist in storage."""
        mock_get_cik.return_value = ("0000320193", "Apple Inc.", "AAPL")

        existing_filing = FilingRecord(
            accession_number="0000320193-24-000010",
            filing_id="000032019324000010",
            cik="0000320193",
            ticker="AAPL",
            company_name="Apple Inc.",
            form_type="10-K",
            filed_at="2024-11-01",
            period_of_report="2024-09-28",
            filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000010/aapl-20240928.htm",
        )
        new_filing = FilingRecord(
            accession_number="0000320193-25-000005",
            filing_id="000032019325000005",
            cik="0000320193",
            ticker="AAPL",
            company_name="Apple Inc.",
            form_type="10-K",
            filed_at="2025-11-01",
            period_of_report="2025-09-27",
            filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000005/aapl-20250927.htm",
        )

        mock_get_recent.return_value = [existing_filing, new_filing]

        with patch("redline.storage.filing_exists") as mock_exists:
            mock_exists.side_effect = lambda fid: fid == "000032019324000010"

            from redline.edgar import get_new_filings

            results = get_new_filings("AAPL", ["10-K"])

        assert len(results) == 1
        assert results[0].filing_id == "000032019325000005"
