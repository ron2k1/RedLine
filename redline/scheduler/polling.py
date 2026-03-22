"""Real-time EDGAR polling scheduler.

Checks for new filings every POLL_INTERVAL_SECONDS during market hours
(9:30-16:00 ET, weekdays). High-score filings trigger alerts.
"""

import json
import logging
import time
from datetime import datetime

from zoneinfo import ZoneInfo

from redline.core import config
from redline.core.models import FilingRecord
from redline.data import storage, watchlist
from redline.ingestion import edgar, extractor
from redline.ingestion.extractor import SECTION_MAP_10K, SECTION_MAP_10Q
from redline.analysis import differ, signals, scorer, analyzer, anomaly
from redline.scheduler.alerts import log_alert

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def _is_market_hours(now_et: datetime) -> bool:
    """Return True if now_et falls within market hours on a weekday."""
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now_et.replace(
        hour=config.MARKET_OPEN_HOUR, minute=config.MARKET_OPEN_MINUTE,
        second=0, microsecond=0,
    )
    market_close = now_et.replace(
        hour=config.MARKET_CLOSE_HOUR, minute=config.MARKET_CLOSE_MINUTE,
        second=0, microsecond=0,
    )
    return market_open <= now_et < market_close


def _seconds_until_market_open(now_et: datetime) -> float:
    """Return seconds until next market open from now_et."""
    # Find the next weekday
    candidate = now_et.replace(
        hour=config.MARKET_OPEN_HOUR, minute=config.MARKET_OPEN_MINUTE,
        second=0, microsecond=0,
    )
    if candidate <= now_et:
        # Move to tomorrow
        from datetime import timedelta
        candidate += timedelta(days=1)
    # Skip weekends
    while candidate.weekday() >= 5:
        from datetime import timedelta
        candidate += timedelta(days=1)
    return (candidate - now_et).total_seconds()


def _sections_for_form(form_type: str, all_sections: list[str]) -> list[str]:
    section_map = SECTION_MAP_10K if form_type.upper().startswith("10-K") else SECTION_MAP_10Q
    return [s for s in all_sections if s in section_map]


def _process_filing_with_alerts(filing: FilingRecord, section_codes: list[str]) -> None:
    """Process a single filing, emitting alerts for high-score diffs.

    Mirrors pipeline.process_filing() but intercepts high-score diffs
    to write alert records.
    """
    logger.info("Processing %s %s %s (period %s)",
                filing.ticker, filing.form_type, filing.filing_id,
                filing.period_of_report)

    results = extractor.extract_all_sections(filing, section_codes)

    for result in results:
        storage.insert_extraction_attempt(
            filing.filing_id, result.section_code,
            result.status, result.error_msg,
        )

        if result.status != "success":
            logger.info("  Section %s: %s", result.section_code, result.status)
            continue

        storage.insert_section(filing.filing_id, result.section_code, result.text)

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

        diff_result = differ.diff_sections(prev_section["raw_text"], result.text)

        if diff_result.pct_changed < config.MIN_PCT_CHANGED:
            logger.info("  Section %s: %.1f%% changed (below threshold)",
                        result.section_code, diff_result.pct_changed * 100)
            continue

        signal_result = signals.detect_signals(result.text)

        anomaly_result = None
        section_emb = anomaly.compute_section_embedding(result.text)
        if section_emb is not None:
            anomaly.store_section_embedding(
                filing.filing_id, result.section_code, section_emb,
            )
            anomaly_result = anomaly.detect_anomaly(
                cik=filing.cik,
                form_type=filing.form_type,
                section=result.section_code,
                current_embedding=section_emb,
            )
            if anomaly_result.is_anomaly:
                logger.info("  Section %s: anomaly detected (z=%.2f)",
                            result.section_code, anomaly_result.z_score)

        prelim = scorer.preliminary_score(diff_result, signal_result)

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
            "diff_version": diff_result.diff_version,
            "semantic_similarity": diff_result.semantic_similarity,
            "sentences_modified": diff_result.sentences_modified,
        }
        storage.insert_diff(diff_dict)
        logger.info("  Section %s: v%d diff stored (prelim=%d, final=%d)",
                    result.section_code, diff_result.diff_version, prelim, final)

        # Alert on high-score diffs
        if final >= config.ALERT_SCORE_THRESHOLD:
            log_alert(diff_dict)

    storage.mark_filing_processed(filing.filing_id)
    logger.info("Marked %s as processed", filing.filing_id)


def _filing_record_to_dict(f: FilingRecord) -> dict:
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


def poll_once() -> int:
    """Run a single polling cycle across all watchlist tickers.

    Returns the number of new filings processed.
    """
    watchlist_data = watchlist.load()
    tickers = watchlist_data.get("tickers", [])
    all_section_codes = watchlist_data.get("sections", ["1A", "7", "3", "9A"])
    form_types = watchlist_data.get("form_types", ["10-K", "10-Q"])

    total_new = 0

    for ticker in tickers:
        cik_result = edgar.get_cik(ticker)
        if not cik_result:
            logger.warning("Could not resolve CIK for %s, skipping", ticker)
            continue

        cik, company_name, canonical_ticker = cik_result
        storage.upsert_company(cik, canonical_ticker, company_name)

        for form_type in form_types:
            filings = edgar.get_new_filings(canonical_ticker, [form_type])

            for filing in filings:
                if storage.filing_exists(filing.filing_id):
                    continue

                storage.insert_filing(filing.filing_id, _filing_record_to_dict(filing))
                codes = _sections_for_form(filing.form_type, all_section_codes)
                _process_filing_with_alerts(filing, codes)
                total_new += 1

    return total_new


def run_scheduler() -> None:
    """Run the polling scheduler loop.

    Polls every POLL_INTERVAL_SECONDS during market hours.
    Sleeps until next market open outside of hours.
    """
    logger.info("=== EDGAR polling scheduler starting ===")
    logger.info("Poll interval: %ds | Market hours: %02d:%02d-%02d:%02d ET | Alert threshold: %d",
                config.POLL_INTERVAL_SECONDS,
                config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE,
                config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE,
                config.ALERT_SCORE_THRESHOLD)

    storage.init_db()

    while True:
        now_et = datetime.now(ET)

        if not _is_market_hours(now_et):
            wait = _seconds_until_market_open(now_et)
            logger.info("Outside market hours. Sleeping %.0f minutes until next open.",
                        wait / 60)
            time.sleep(wait)
            continue

        logger.info("Polling EDGAR for new filings at %s ET", now_et.strftime("%H:%M:%S"))
        try:
            count = poll_once()
            if count:
                logger.info("Processed %d new filing(s) this cycle", count)
            else:
                logger.info("No new filings found")
        except Exception:
            logger.exception("Error during polling cycle")

        time.sleep(config.POLL_INTERVAL_SECONDS)
