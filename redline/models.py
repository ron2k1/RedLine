from dataclasses import dataclass, field


@dataclass
class FilingRecord:
    """Canonical shape flowing edgar.py -> extractor.py -> pipeline.py.
    filing_id is the canonical key for ALL storage APIs."""
    accession_number: str   # with dashes: 0001234567-24-000001
    filing_id: str          # dashes removed: 000123456724000001 -- CANONICAL DB KEY
    cik: str                # zero-padded 10-digit
    ticker: str             # SEC-canonical form (e.g. BRK-B, not BRK.B)
    company_name: str       # resolved alongside CIK
    form_type: str          # '10-K' or '10-Q'
    filed_at: str           # ISO datetime
    period_of_report: str   # YYYY-MM-DD
    filing_url: str         # full EDGAR URL to primary document


@dataclass
class ExtractionResult:
    """Output of extractor.extract_section(). Rich enough for both
    storage.insert_extraction_attempt() and UI display."""
    section_code: str       # '1A', '7', '3', '9A'
    status: str             # 'success' | 'failed' | 'not_found'
    text: str | None        # plain text on success, None otherwise
    error_msg: str | None   # None on success, diagnostic string on failure


@dataclass
class DiffResult:
    pct_changed: float
    word_count_old: int
    word_count_new: int
    word_count_delta: int
    sentences_added: int
    sentences_removed: int
    sentences_unchanged: int
    diff_preview: str           # max 3000 chars
    raw_chunks: list[dict] = field(default_factory=list)


@dataclass
class SignalResult:
    triggered: bool
    signals: list[dict] = field(default_factory=list)
    max_severity: int = 0
    flags_json: str = "[]"
