"""Tests for redline.extractor — SEC filing section extraction."""

from unittest.mock import patch, MagicMock

from redline.extractor import extract_section, extract_all_sections
from redline.models import FilingRecord, ExtractionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_filing(**overrides) -> FilingRecord:
    """Return a realistic FilingRecord suitable for testing."""
    defaults = dict(
        accession_number="0001234567-24-000001",
        filing_id="000123456724000001",
        cik="0001234567",
        ticker="ACME",
        company_name="Acme Corp",
        form_type="10-K",
        filed_at="2024-03-15T00:00:00",
        period_of_report="2023-12-31",
        filing_url="https://www.sec.gov/Archives/edgar/data/1234567/filing.htm",
    )
    defaults.update(overrides)
    return FilingRecord(**defaults)


# A minimal HTML document with clearly delimited Item sections.
_SAMPLE_HTML = """
<html><body>
<h2>Table of Contents</h2>
<p>Item 1A - Risk Factors ....... 10</p>
<p>Item 7 - MD&amp;A ............... 40</p>

<h2>Item 1A. Risk Factors</h2>
<p>The company faces significant <b>market risks</b> including
interest rate fluctuations, credit risk, and operational disruptions
that could materially affect our financial results and overall
business performance going forward into the next fiscal year.</p>

<h2>Item 7. Management's Discussion and Analysis</h2>
<p>Revenue increased 12% year over year driven by strong demand
across all segments and improved pricing strategies implemented
during the second quarter of the reporting period.</p>

<h2>Item 9A. Controls and Procedures</h2>
<p>Management assessed the effectiveness of the company's internal
controls over financial reporting as of the period ending date and
concluded that such controls were effective and operating as designed.</p>
</body></html>
"""

# HTML that contains NO recognizable Item headers at all.
_EMPTY_HTML = """
<html><body>
<h1>Annual Report</h1>
<p>This document contains no standard Item headers.</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("redline.extractor.requests.get")
def test_success_extraction(mock_get):
    """Successful extraction returns status='success' with clean plain text."""
    mock_resp = MagicMock()
    mock_resp.text = _SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    filing = _make_filing()
    result = extract_section(filing, "1A")

    assert isinstance(result, ExtractionResult)
    assert result.status == "success"
    assert result.text is not None
    assert len(result.text) > 0
    assert result.error_msg is None
    assert result.section_code == "1A"


@patch("redline.extractor.requests.get")
def test_not_found_no_matching_section(mock_get):
    """When the target section doesn't exist in the HTML, status='not_found'."""
    mock_resp = MagicMock()
    mock_resp.text = _EMPTY_HTML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    filing = _make_filing()
    result = extract_section(filing, "1A")

    assert result.status == "not_found"
    assert result.text is None


@patch("redline.extractor.requests.get")
def test_failed_on_request_exception(mock_get):
    """When requests.get raises, status='failed' with error_msg set."""
    mock_get.side_effect = ConnectionError("Network unreachable")

    filing = _make_filing()
    result = extract_section(filing, "1A")

    assert result.status == "failed"
    assert result.text is None
    assert result.error_msg is not None
    assert "Network unreachable" in result.error_msg


@patch("redline.extractor.requests.get")
def test_no_html_tags_in_output(mock_get):
    """Extracted text must not contain HTML angle brackets."""
    mock_resp = MagicMock()
    mock_resp.text = _SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    filing = _make_filing()
    result = extract_section(filing, "1A")

    assert result.status == "success"
    assert "<" not in result.text
    assert ">" not in result.text


@patch("redline.extractor.requests.get")
def test_extract_all_sections(mock_get):
    """extract_all_sections returns one ExtractionResult per code."""
    mock_resp = MagicMock()
    mock_resp.text = _SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    filing = _make_filing()
    codes = ["1A", "7", "9A"]
    results = extract_all_sections(filing, codes)

    assert len(results) == len(codes)
    for r in results:
        assert isinstance(r, ExtractionResult)
    returned_codes = [r.section_code for r in results]
    assert returned_codes == codes


@patch("redline.extractor.requests.get")
def test_unmapped_section_code(mock_get):
    """A section code not in the map yields status='not_found' with error_msg."""
    mock_resp = MagicMock()
    mock_resp.text = _SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    filing = _make_filing()
    result = extract_section(filing, "99Z")

    assert result.status == "not_found"
    assert result.text is None
    assert result.error_msg is not None
    assert "not mapped" in result.error_msg


@patch("redline.extractor.requests.get")
def test_10q_uses_correct_section_map(mock_get):
    """A 10-Q filing uses SECTION_MAP_10Q, so section code '2' is valid."""
    html_10q = """
    <html><body>
    <h2>Item 2. Management's Discussion and Analysis</h2>
    <p>Quarterly revenue was flat compared to the prior quarter. Operating
    expenses increased modestly due to seasonal hiring. The company maintained
    its guidance for the remainder of the fiscal year despite headwinds.</p>
    <h2>Item 3. Quantitative and Qualitative Disclosures</h2>
    <p>Disclosures content here.</p>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.text = html_10q
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    filing = _make_filing(form_type="10-Q")
    result = extract_section(filing, "2")

    assert result.status == "success"
    assert result.text is not None
    assert "revenue" in result.text.lower()
