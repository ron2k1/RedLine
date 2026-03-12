"""Pattern signal detector — scans diff text for financial red flag patterns."""

import json
import re

from redline.models import SignalResult

# Each entry: (signal name, severity, list of regex patterns)
SIGNAL_PATTERNS: list[tuple[str, int, list[str]]] = [
    (
        "going_concern",
        9,
        [
            r"going concern",
            r"ability to continue as a going concern",
            r"substantial doubt about .* ability to continue",
        ],
    ),
    (
        "auditor_change",
        7,
        [
            r"change in auditor",
            r"dismissed .* accountant",
            r"engaged .* as .* new .* auditor",
            r"change of accountant",
        ],
    ),
    (
        "restatement",
        8,
        [
            r"restatement of .* financial",
            r"restated .* previously reported",
            r"correcting .* error",
        ],
    ),
    (
        "material_weakness",
        7,
        [
            r"material weakness",
            r"significant deficiency in internal control",
        ],
    ),
    (
        "goodwill_impairment",
        6,
        [
            r"goodwill impairment",
            r"impairment of goodwill",
            r"wrote down .* goodwill",
        ],
    ),
    (
        "revenue_recognition_change",
        5,
        [
            r"change in revenue recognition",
            r"revised .* revenue .* policy",
            r"adoption of .* ASC 606",
        ],
    ),
    (
        "debt_covenant_violation",
        8,
        [
            r"covenant violation",
            r"breach of .* covenant",
            r"waiver .* from .* lender",
            r"non-compliance with .* debt",
        ],
    ),
    (
        "related_party_transaction",
        5,
        [
            r"related.party transaction",
            r"transaction.* with .* related part",
        ],
    ),
    (
        "litigation_risk",
        4,
        [
            r"pending litigation",
            r"legal proceedings .* material",
            r"class action .* filed",
        ],
    ),
]


def detect_signals(text: str) -> SignalResult:
    """Scan *text* for financial red-flag patterns.

    Returns a SignalResult with all matched signals, their severities,
    and the matched text fragments.
    """
    signals: list[dict] = []

    for signal_name, severity, patterns in SIGNAL_PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                signals.append(
                    {
                        "signal": signal_name,
                        "severity": severity,
                        "matched_text": match.group(0),
                    }
                )
                break  # one match per signal is enough

    triggered = len(signals) > 0
    max_severity = max((s["severity"] for s in signals), default=0)
    flags_json = json.dumps(signals)

    return SignalResult(
        triggered=triggered,
        signals=signals,
        max_severity=max_severity,
        flags_json=flags_json,
    )
