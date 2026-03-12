"""Section extractor for SEC filings.

Fetches filing HTML from EDGAR, locates Item sections via regex,
strips HTML to plain text, returns ExtractionResult per section.
"""

import re
import logging

import requests

from redline import config
from redline.models import FilingRecord, ExtractionResult

logger = logging.getLogger(__name__)

# Map section codes to the Item headers used in 10-K and 10-Q filings.
SECTION_MAP_10K: dict[str, str] = {
    "1A": "Item 1A",   # Risk Factors
    "7":  "Item 7",    # MD&A
    "9A": "Item 9A",   # Controls and Procedures
}

SECTION_MAP_10Q: dict[str, str] = {
    "1A": "Item 1A",   # Risk Factors
    "2":  "Item 2",    # MD&A (Part I, Item 2 in 10-Q)
    "3":  "Item 3",    # Quantitative and Qualitative Disclosures
}

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Matches an Item header like "Item 1A", "ITEM 7", "Item 9A." etc.
# Captures the item number+letter so we can compare which item we found.
# Anchored loosely: preceded by a tag close, newline, or start-of-string.
_ITEM_HEADER_RE = re.compile(
    r'(?:^|>|\n)\s*'           # anchor: start, closing tag, or newline
    r'(?:ITEM|Item|item)\s+'   # literal "Item" (case-insensitive via alternation)
    r'(\d+[A-Za-z]?)'         # capture group: item number, e.g. "1A", "7"
    r'\s*[\.\-:—\s]',         # separator after the number
)


def _clean_html(text: str) -> str:
    """Remove HTML tags, decode common entities, collapse whitespace."""
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common HTML entities
    for entity, char in (
        ('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
        ('&nbsp;', ' '), ('&#160;', ' '), ('&quot;', '"'),
        ('&#39;', "'"), ('&apos;', "'"),
    ):
        text = text.replace(entity, char)
    # Remove any remaining angle brackets (partial tags at extraction boundaries)
    text = text.replace('<', ' ').replace('>', ' ')
    # Collapse runs of whitespace into a single space
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _section_map_for(form_type: str) -> dict[str, str]:
    """Return the section map appropriate for *form_type*."""
    if form_type.upper().startswith("10-K"):
        return SECTION_MAP_10K
    return SECTION_MAP_10Q


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_section(filing: FilingRecord, section_code: str) -> ExtractionResult:
    """Extract a single section from a filing.

    Strategy:
    1. Choose the section map for the filing's form type.
    2. Fetch the filing document HTML from ``filing.filing_url``.
    3. Scan for all Item headers.  Identify the target item's content span
       (from its header to the next item header).
    4. Strip HTML to produce plain text.
    5. Return an ``ExtractionResult`` with status ``'success'``,
       ``'not_found'``, or ``'failed'``.
    """
    try:
        section_map = _section_map_for(filing.form_type)

        if section_code not in section_map:
            return ExtractionResult(
                section_code=section_code,
                status="not_found",
                text=None,
                error_msg=f"Section {section_code} not mapped for {filing.form_type}",
            )

        target_item_num = section_map[section_code].replace("Item ", "")

        # ----- fetch ---------------------------------------------------------
        headers = {"User-Agent": config.SEC_USER_AGENT}
        resp = requests.get(filing.filing_url, headers=headers, timeout=30)
        resp.raise_for_status()
        html = resp.text

        # ----- locate all Item headers in order ------------------------------
        matches = list(_ITEM_HEADER_RE.finditer(html))
        if not matches:
            return ExtractionResult(
                section_code=section_code,
                status="not_found",
                text=None,
                error_msg=None,
            )

        # Collect positions where our target item appears.
        target_hits = [
            m for m in matches
            if m.group(1).upper() == target_item_num.upper()
        ]

        if not target_hits:
            return ExtractionResult(
                section_code=section_code,
                status="not_found",
                text=None,
                error_msg=None,
            )

        # Heuristic: skip the first occurrence when there are multiple, since
        # the first is usually the Table of Contents entry.
        start_match = target_hits[1] if len(target_hits) > 1 else target_hits[0]
        start_pos = start_match.start()

        # ----- find the *next* Item header after our start -------------------
        subsequent = [
            m for m in matches
            if m.start() > start_match.end()
            and m.group(1).upper() != target_item_num.upper()
        ]

        if subsequent:
            end_pos = subsequent[0].start()
        else:
            # No following header found — take up to 500 KB.
            end_pos = min(start_pos + 500_000, len(html))

        section_html = html[start_pos:end_pos]

        # ----- clean to plain text -------------------------------------------
        text = _clean_html(section_html)

        if not text or len(text) < 50:
            return ExtractionResult(
                section_code=section_code,
                status="not_found",
                text=None,
                error_msg=None,
            )

        return ExtractionResult(
            section_code=section_code,
            status="success",
            text=text,
            error_msg=None,
        )

    except Exception as e:
        logger.error(
            "Extraction failed for %s section %s: %s",
            filing.filing_id, section_code, e,
        )
        return ExtractionResult(
            section_code=section_code,
            status="failed",
            text=None,
            error_msg=str(e),
        )


def extract_all_sections(
    filing: FilingRecord,
    section_codes: list[str],
) -> list[ExtractionResult]:
    """Extract every requested section from *filing*, returning one
    ``ExtractionResult`` per section code (same order)."""
    results: list[ExtractionResult] = []
    for code in section_codes:
        result = extract_section(filing, code)
        results.append(result)
    return results
