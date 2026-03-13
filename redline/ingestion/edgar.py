"""SEC EDGAR poller — all EDGAR API communication for Redline.

Resolves tickers to CIKs via company_tickers.json, fetches filing metadata
from the submissions API, and identifies new filings not yet in the database.
Enforces SEC rate limits (max 10 req/sec) with exponential backoff on 429s.
"""

import time
import logging
import requests
from datetime import datetime, timedelta

from redline.core import config
from redline.core.models import FilingRecord

logger = logging.getLogger(__name__)

_last_request_time = 0.0
_RATE_LIMIT_INTERVAL = 0.1  # 10 requests/sec max


def _rate_limit():
    """Enforce max 10 requests/sec to SEC EDGAR."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _RATE_LIMIT_INTERVAL:
        time.sleep(_RATE_LIMIT_INTERVAL - elapsed)
    _last_request_time = time.time()


def _get(url: str, max_retries: int = 3) -> requests.Response:
    """GET with User-Agent header, rate limiting, and exponential backoff on 429."""
    headers = {"User-Agent": config.SEC_USER_AGENT}
    for attempt in range(max_retries):
        _rate_limit()
        resp = requests.get(url, headers=headers)
        if resp.status_code == 429:
            wait = 2 ** attempt
            logger.warning(f"429 from EDGAR, backing off {wait}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise Exception(f"EDGAR request failed after {max_retries} retries: {url}")


def get_cik(ticker: str) -> tuple[str, str, str] | None:
    """Resolve ticker to (cik_padded_10digits, company_name, canonical_ticker) or None.

    Uses https://www.sec.gov/files/company_tickers.json
    - Normalizes input: uppercase, replace '.' with '-' to match SEC canonical form
    - Searches for matching ticker
    - Pads CIK to 10 digits with leading zeros
    - Returns (cik_padded, company_name, canonical_ticker) or None
    """
    normalized = ticker.upper().replace(".", "-")
    resp = _get("https://www.sec.gov/files/company_tickers.json")
    data = resp.json()

    for entry in data.values():
        sec_ticker = entry["ticker"].upper()
        if sec_ticker == normalized:
            cik_padded = str(entry["cik_str"]).zfill(10)
            company_name = entry["title"]
            canonical_ticker = sec_ticker
            return (cik_padded, company_name, canonical_ticker)

    return None


def _parse_filings_block(block: dict, cik: str, ticker: str,
                         company_name: str,
                         form_types: list[str],
                         cutoff_date: str | None) -> list[FilingRecord]:
    """Parse a parallel-array filings block into FilingRecord objects.

    block has keys: accessionNumber, form, filingDate, reportDate,
    primaryDocument, etc. — all lists of the same length.
    """
    records = []
    accession_numbers = block.get("accessionNumber", [])
    forms = block.get("form", [])
    filing_dates = block.get("filingDate", [])
    report_dates = block.get("reportDate", [])
    primary_docs = block.get("primaryDocument", [])

    cik_int = str(int(cik))  # strip leading zeros for URL path

    for i in range(len(accession_numbers)):
        form = forms[i]
        if form not in form_types:
            continue

        report_date = report_dates[i]
        if cutoff_date and report_date < cutoff_date:
            continue

        accession = accession_numbers[i]  # with dashes
        filing_id = accession.replace("-", "")
        accession_no_dashes = accession.replace("-", "")
        primary_doc = primary_docs[i]

        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_int}/{accession_no_dashes}/{primary_doc}"
        )

        record = FilingRecord(
            accession_number=accession,
            filing_id=filing_id,
            cik=cik,
            ticker=ticker,
            company_name=company_name,
            form_type=form,
            filed_at=filing_dates[i],
            period_of_report=report_date,
            filing_url=filing_url,
        )
        records.append(record)

    return records


def get_recent_filings(cik: str, form_types: list[str], ticker: str,
                       company_name: str,
                       max_years: int | None = None) -> list[FilingRecord]:
    """Fetch filings from EDGAR submissions API.

    1. Fetch https://data.sec.gov/submissions/CIK{cik_padded}.json
    2. Parse recent filings from response['filings']['recent']
    3. If max_years is set, also follow response['filings']['files'] for older data
    4. Filter by form_type and max_years cutoff
    5. Return sorted by period_of_report ASC (oldest first)
    """
    cutoff_date = None
    if max_years is not None:
        cutoff = datetime.now() - timedelta(days=max_years * 365)
        cutoff_date = cutoff.strftime("%Y-%m-%d")

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = _get(url)
    data = resp.json()

    filings_data = data["filings"]
    recent = filings_data["recent"]

    records = _parse_filings_block(
        recent, cik, ticker, company_name, form_types, cutoff_date
    )

    # Follow paginated files for older history when max_years is set
    if max_years is not None:
        files_list = filings_data.get("files", [])
        for file_entry in files_list:
            filename = file_entry["name"]
            file_url = f"https://data.sec.gov/submissions/{filename}"
            file_resp = _get(file_url)
            file_data = file_resp.json()
            records.extend(
                _parse_filings_block(
                    file_data, cik, ticker, company_name,
                    form_types, cutoff_date
                )
            )

    # Sort oldest first by period_of_report
    records.sort(key=lambda r: r.period_of_report)
    return records


def get_new_filings(ticker: str,
                    form_types: list[str]) -> list[FilingRecord]:
    """Get filings not yet in database.

    1. Resolve ticker via get_cik()
    2. Fetch recent filings (no max_years)
    3. Filter out any already stored (storage.filing_exists)
    4. Return remaining, sorted oldest first
    """
    result = get_cik(ticker)
    if result is None:
        logger.warning(f"Could not resolve ticker: {ticker}")
        return []

    cik, company_name, canonical_ticker = result

    filings = get_recent_filings(
        cik, form_types, canonical_ticker, company_name
    )

    # Lazy import to avoid circular imports
    from redline.data import storage

    new_filings = [
        f for f in filings
        if not storage.filing_exists(f.filing_id)
    ]

    # Already sorted oldest first from get_recent_filings
    return new_filings
