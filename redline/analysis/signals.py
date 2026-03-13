"""Pattern signal detector — scans diff text for financial red flag patterns."""

import json
import re

from redline.core.models import SignalResult

# Each entry: (signal name, severity, list of regex patterns)
# All patterns run with re.IGNORECASE.  Design principles:
#   - \b word boundaries on every pattern to prevent partial matches
#   - .{0,N} instead of .* to prevent runaway greedy matching
#   - (?:...) non-capturing groups for optional SEC wording variants
#   - [-\s]? for hyphen/space variation common in filings
SIGNAL_PATTERNS: list[tuple[str, int, list[str]]] = [
    (
        "going_concern",
        9,
        [
            r"\bgoing concern\b",
            r"\bability to continue as a going concern\b",
            r"\bsubstantial doubt (?:exists )?about (?:the company'?s |its )?ability to continue\b",
            r"\braise[sd]? substantial doubt\b",
        ],
    ),
    (
        "auditor_change",
        7,
        [
            r"\bchange (?:in|of) (?:the )?auditor\b",
            r"\bdismissed (?:its |the )?(?:former )?(?:independent )?(?:registered )?(?:public )?account(?:ant|ing firm)\b",
            r"\bengaged .{0,60} as (?:its )?(?:new )?(?:independent )?auditor\b",
            r"\bchange of accountant\b",
            r"\bprincipal accountant (?:resigned|was dismissed)\b",
        ],
    ),
    (
        "restatement",
        8,
        [
            r"\brestatement of (?:its |the )?(?:previously issued |previously reported )?financial (?:statements?|results)\b",
            r"\brestated (?:its )?(?:previously reported )?financial (?:statements?|results)\b",
            r"\bcorrect(?:ed|ing) (?:an )?error in (?:its |the )?(?:previously reported )?financial (?:statements?|results)\b",
        ],
    ),
    (
        "material_weakness",
        7,
        [
            r"\bmaterial weakness(?:es)?\b",
            r"\bsignificant deficienc(?:y|ies) in internal control\b",
            r"\bmaterial weakness(?:es)? in (?:its )?internal control(?:s)?\b",
        ],
    ),
    (
        "goodwill_impairment",
        6,
        [
            r"\bgoodwill impairment\b",
            r"\bimpairment of goodwill\b",
            r"\bwrote down .{0,30}goodwill\b",
            r"\brecorded (?:a |an )?goodwill impairment (?:charge|loss)\b",
            r"\bgoodwill write[-\s]?down\b",
        ],
    ),
    (
        "revenue_recognition_change",
        5,
        [
            r"\bchange in revenue recognition\b",
            r"\brevised .{0,40}revenue recognition polic(?:y|ies)\b",
            r"\badoption of (?:the )?ASC 606\b",
            r"\bchange in .{0,30}revenue .{0,20}polic(?:y|ies)\b",
        ],
    ),
    (
        "debt_covenant_violation",
        8,
        [
            r"\bcovenant violation\b",
            r"\bbreach of (?:a |its )?(?:financial )?covenant\b",
            r"\bwaiver (?:was )?(?:obtained )?from (?:the |its )?lender\b",
            r"\bnon[-\s]?compliance with (?:its )?debt\b",
            r"\bdefault under (?:the |its )?(?:credit|loan) (?:agreement|facility)\b",
        ],
    ),
    (
        "related_party_transaction",
        5,
        [
            r"\brelated[-\s]?party transaction(?:s)?\b",
            r"\btransaction(?:s)? with (?:a |an |the )?related part(?:y|ies)\b",
        ],
    ),
    (
        "litigation_risk",
        4,
        [
            r"\bpending litigation\b",
            r"\blegal proceedings .{0,40}material\b",
            r"\bclass[-\s]?action (?:complaint |lawsuit |suit )?(?:was |has been )?filed\b",
            r"\bmaterial litigation\b",
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
