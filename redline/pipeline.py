"""Master pipeline — orchestrates backfill, daily polling, and crash recovery.

run() is the single entry point. process_filing() is the shared function
used by all three paths (backfill, daily, resume).
"""

import json
import logging

from redline import config, storage, edgar, extractor, differ, signals, scorer, analyzer, watchlist
from redline.models import FilingRecord

logger = logging.getLogger(__name__)


def _filing_record_from_dict(d: dict) -> FilingRecord:
    """Reconstruct a FilingRecord from a storage row dict."""
    return FilingRecord(
        accession_number=d["accession_number"],
        filing_id=d["id"],
        cik=d["cik"],
        ticker=d["ticker"],
        company_name=d["company_name"],
        form_type=d["form_type"],
        filed_at=d["filed_at"],
        period_of_report=d["period_of_report"],
        filing_url=d["filing_url"],
    )


def _filing_record_to_dict(f: FilingRecord) -> dict:
    """Convert a FilingRecord to the dict expected by storage.insert_filing()."""
    return {
        "cik": f.cik,
        "ticker": f.ticker,
        "company_name": f.company_name,
        "form_type": f.form_type,
        "filed_at": f.filed_at,
        "period_of_report": f.period_of_report,
        "filing_url": f.filing_url,
        "accession_number": f.accession_number,
    }


def process_filing(filing: FilingRecord, section_codes: list[str]) -> None:
    """Process a single filing — extract, diff, score, maybe LLM, store.

    Used by all three paths: backfill, daily polling, and crash recovery.
    """
    logger.info("Processing %s %s %s (period %s)",
                filing.ticker, filing.form_type, filing.filing_id,
                filing.period_of_report)

    results = extractor.extract_all_sections(filing, section_codes)

    for result in results:
        # Store every extraction attempt
        storage.insert_extraction_attempt(
            filing.filing_id, result.section_code,
            result.status, result.error_msg,
        )

        if result.status != "success":
            logger.info("  Section %s: %s", result.section_code, result.status)
            continue

        # Store the extracted text
        storage.insert_section(filing.filing_id, result.section_code, result.text)

        # Find previous filing for diffing
        prev = storage.get_previous_filing(
            filing.cik, filing.form_type, filing.period_of_report,
        )
        if not prev:
            logger.info("  Section %s: no previous filing to diff against",
                        result.section_code)
            continue

        prev_section = storage.get_section(prev["id"], result.section_code)
        if not prev_section:
            logger.info("  Section %s: previous filing has no text for this section",
                        result.section_code)
            continue

        # Diff
        diff_result = differ.diff_sections(prev_section["raw_text"], result.text)

        if diff_result.pct_changed < config.MIN_PCT_CHANGED:
            logger.info("  Section %s: %.1f%% changed (below threshold)",
                        result.section_code, diff_result.pct_changed * 100)
            continue

        # Detect signals
        signal_result = signals.detect_signals(result.text)

        # Score
        prelim = scorer.preliminary_score(diff_result, signal_result)

        # Maybe run LLM analysis
        llm_output = None
        final = prelim
        if prelim >= config.PRELIMINARY_SCORE_LLM_THRESHOLD:
            logger.info("  Section %s: prelim score %d >= threshold, running LLM",
                        result.section_code, prelim)
            llm_output = analyzer.analyze_diff(
                ticker=filing.ticker,
                form_type=filing.form_type,
                period=filing.period_of_report,
                section=result.section_code,
                diff_preview=diff_result.diff_preview,
                signals_json=signal_result.flags_json,
            )
            if llm_output:
                final = scorer.final_score(
                    prelim, llm_output.get("severity_score"),
                )

        # Store the diff
        diff_dict = {
            "filing_id": filing.filing_id,
            "prev_filing_id": prev["id"],
            "section": result.section_code,
            "ticker": filing.ticker,
            "form_type": filing.form_type,
            "period_of_report": filing.period_of_report,
            "pct_changed": diff_result.pct_changed,
            "word_count_old": diff_result.word_count_old,
            "word_count_new": diff_result.word_count_new,
            "word_count_delta": diff_result.word_count_delta,
            "sentences_added": diff_result.sentences_added,
            "sentences_removed": diff_result.sentences_removed,
            "sentences_unchanged": diff_result.sentences_unchanged,
            "diff_preview": diff_result.diff_preview,
            "preliminary_score": prelim,
            "final_score": final,
            "flags_json": signal_result.flags_json,
            "llm_output": json.dumps(llm_output) if llm_output else None,
        }
        storage.insert_diff(diff_dict)
        logger.info("  Section %s: diff stored (prelim=%d, final=%d)",
                    result.section_code, prelim, final)

    storage.mark_filing_processed(filing.filing_id)
    logger.info("Marked %s as processed", filing.filing_id)


def run() -> None:
    """Main pipeline entry point.

    1. init_db()
    2. Resume stranded filings (processed=0)
    3. Per ticker in watchlist: backfill or poll per form_type
    4. Log summary
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger.info("=== Redline pipeline starting ===")
    storage.init_db()

    watchlist_data = watchlist.load()
    section_codes = watchlist_data.get("sections", ["1A", "7", "3", "9A"])
    form_types = watchlist_data.get("form_types", ["10-K", "10-Q"])

    # 1. Resume any stranded filings from prior crashed runs
    unprocessed = storage.get_unprocessed_filings()
    if unprocessed:
        logger.info("Resuming %d unprocessed filings from previous run",
                    len(unprocessed))
        for filing_dict in unprocessed:
            filing = _filing_record_from_dict(filing_dict)
            process_filing(filing, section_codes)

    # 2. Normal polling / backfill per ticker
    tickers = watchlist_data.get("tickers", [])
    total_new = 0

    for ticker in tickers:
        logger.info("--- Processing ticker: %s ---", ticker)

        cik_result = edgar.get_cik(ticker)
        if not cik_result:
            logger.warning("Could not resolve CIK for %s, skipping", ticker)
            continue

        cik, company_name, canonical_ticker = cik_result
        storage.upsert_company(cik, canonical_ticker, company_name)

        for form_type in form_types:
            count = storage.get_filing_count(cik, form_type)

            if count == 0:
                # Backfill: fetch 5 years of history
                logger.info("Backfilling %s %s (5-year history)",
                            canonical_ticker, form_type)
                filings = edgar.get_recent_filings(
                    cik, [form_type], canonical_ticker, company_name,
                    max_years=config.BACKFILL_YEARS,
                )
            else:
                # Daily polling: just recent filings not in DB
                filings = edgar.get_new_filings(canonical_ticker, [form_type])

            # Process each new filing (oldest first)
            for filing in filings:
                if storage.filing_exists(filing.filing_id):
                    continue

                storage.insert_filing(filing.filing_id, _filing_record_to_dict(filing))
                process_filing(filing, section_codes)
                total_new += 1

    logger.info("=== Pipeline complete. %d new filings processed. ===", total_new)


if __name__ == "__main__":
    run()
