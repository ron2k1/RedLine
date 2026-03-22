"""Alert logging for high-score filings.

Appends structured JSON lines to alerts/alerts.jsonl when a filing's
final_score meets or exceeds the configured threshold.
"""

import json
import logging
import os
from datetime import datetime, timezone

from redline.core import config

logger = logging.getLogger(__name__)


def log_alert(diff_dict: dict) -> None:
    """Append an alert record to the JSONL alerts file.

    Args:
        diff_dict: The diff dictionary as built by pipeline.process_filing().
    """
    alert = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": diff_dict["ticker"],
        "filing_id": diff_dict["filing_id"],
        "form_type": diff_dict["form_type"],
        "period_of_report": diff_dict["period_of_report"],
        "section": diff_dict["section"],
        "preliminary_score": diff_dict["preliminary_score"],
        "final_score": diff_dict["final_score"],
        "pct_changed": diff_dict["pct_changed"],
        "flags_json": diff_dict["flags_json"],
    }

    alerts_path = config.ALERTS_PATH
    os.makedirs(os.path.dirname(alerts_path), exist_ok=True)

    with open(alerts_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(alert) + "\n")

    logger.warning(
        "ALERT: %s %s section %s scored %d (filing %s)",
        alert["ticker"], alert["form_type"], alert["section"],
        alert["final_score"], alert["filing_id"],
    )


def get_alert_summary() -> dict:
    """Read alerts/alerts.jsonl and return a summary dictionary.

    Returns:
        A dict with:
        - total_alerts (int): Total number of alert records.
        - high_score_count (int): Number of alerts with final_score >= 8.
        - latest_alert (dict or None): The last alert record, or None if empty.
    """
    alerts_path = config.ALERTS_PATH

    if not os.path.exists(alerts_path):
        return {
            "total_alerts": 0,
            "high_score_count": 0,
            "latest_alert": None,
        }

    total_alerts = 0
    high_score_count = 0
    latest_alert = None

    with open(alerts_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            alert = json.loads(line)
            total_alerts += 1
            if alert.get("final_score", 0) >= 8:
                high_score_count += 1
            latest_alert = alert

    return {
        "total_alerts": total_alerts,
        "high_score_count": high_score_count,
        "latest_alert": latest_alert,
    }
