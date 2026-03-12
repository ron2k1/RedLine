"""Tests for redline.signals — pattern signal detector."""

import json

from redline.signals import detect_signals


# ── Going concern ────────────────────────────────────────────────────────

def test_going_concern_positive():
    result = detect_signals("There is substantial doubt about the company's ability to continue as a going concern.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "going_concern"]
    assert len(match) == 1
    assert match[0]["severity"] == 9


def test_going_concern_negative():
    result = detect_signals("The company reported strong quarterly earnings and robust cash flows.")
    match = [s for s in result.signals if s["signal"] == "going_concern"]
    assert len(match) == 0


# ── Auditor change ───────────────────────────────────────────────────────

def test_auditor_change_positive():
    result = detect_signals("The board dismissed the former accountant and engaged a new firm.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "auditor_change"]
    assert len(match) == 1
    assert match[0]["severity"] == 7


def test_auditor_change_negative():
    result = detect_signals("The independent auditor issued an unqualified opinion.")
    match = [s for s in result.signals if s["signal"] == "auditor_change"]
    assert len(match) == 0


# ── Restatement ──────────────────────────────────────────────────────────

def test_restatement_positive():
    result = detect_signals("The company announced a restatement of its financial statements for Q3.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "restatement"]
    assert len(match) == 1
    assert match[0]["severity"] == 8


def test_restatement_negative():
    result = detect_signals("Financial statements were prepared in accordance with GAAP.")
    match = [s for s in result.signals if s["signal"] == "restatement"]
    assert len(match) == 0


# ── Material weakness ────────────────────────────────────────────────────

def test_material_weakness_positive():
    result = detect_signals("Management identified a material weakness in internal controls over financial reporting.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "material_weakness"]
    assert len(match) == 1
    assert match[0]["severity"] == 7


def test_material_weakness_negative():
    result = detect_signals("Internal controls were effective as of the report date.")
    match = [s for s in result.signals if s["signal"] == "material_weakness"]
    assert len(match) == 0


# ── Goodwill impairment ──────────────────────────────────────────────────

def test_goodwill_impairment_positive():
    result = detect_signals("The firm recorded a goodwill impairment charge of $200 million.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "goodwill_impairment"]
    assert len(match) == 1
    assert match[0]["severity"] == 6


def test_goodwill_impairment_negative():
    result = detect_signals("Goodwill remained unchanged from the prior year at $1.2 billion.")
    match = [s for s in result.signals if s["signal"] == "goodwill_impairment"]
    assert len(match) == 0


# ── Revenue recognition change ───────────────────────────────────────────

def test_revenue_recognition_change_positive():
    result = detect_signals("The company completed its adoption of the ASC 606 revenue standard.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "revenue_recognition_change"]
    assert len(match) == 1
    assert match[0]["severity"] == 5


def test_revenue_recognition_change_negative():
    result = detect_signals("Revenue increased 12% year-over-year driven by new product sales.")
    match = [s for s in result.signals if s["signal"] == "revenue_recognition_change"]
    assert len(match) == 0


# ── Debt covenant violation ──────────────────────────────────────────────

def test_debt_covenant_violation_positive():
    result = detect_signals("The borrower was in breach of its financial covenant under the credit agreement.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "debt_covenant_violation"]
    assert len(match) == 1
    assert match[0]["severity"] == 8


def test_debt_covenant_violation_negative():
    result = detect_signals("All debt covenants were satisfied as of year-end.")
    match = [s for s in result.signals if s["signal"] == "debt_covenant_violation"]
    assert len(match) == 0


# ── Related party transaction ────────────────────────────────────────────

def test_related_party_transaction_positive():
    result = detect_signals("The company entered into a related-party transaction with an entity controlled by the CEO.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "related_party_transaction"]
    assert len(match) == 1
    assert match[0]["severity"] == 5


def test_related_party_transaction_negative():
    result = detect_signals("All transactions were conducted at arm's length with independent parties.")
    match = [s for s in result.signals if s["signal"] == "related_party_transaction"]
    assert len(match) == 0


# ── Litigation risk ──────────────────────────────────────────────────────

def test_litigation_risk_positive():
    result = detect_signals("A class action lawsuit was filed against the company in Delaware.")
    assert result.triggered is True
    match = [s for s in result.signals if s["signal"] == "litigation_risk"]
    assert len(match) == 1
    assert match[0]["severity"] == 4


def test_litigation_risk_negative():
    result = detect_signals("There are no material legal proceedings pending against the registrant.")
    match = [s for s in result.signals if s["signal"] == "litigation_risk"]
    assert len(match) == 0


# ── No signals ───────────────────────────────────────────────────────────

def test_no_signals():
    result = detect_signals("The company had a great quarter with record revenue and profit margins.")
    assert result.triggered is False
    assert result.signals == []
    assert result.max_severity == 0
    assert result.flags_json == "[]"


# ── Multiple signals ─────────────────────────────────────────────────────

def test_multiple_signals():
    text = (
        "There is substantial doubt about the entity's ability to continue as a going concern. "
        "Management also identified a material weakness in its internal controls. "
        "Additionally, a class action was filed in federal court last month. "
        "The company announced a restatement of its financial results for Q2."
    )
    result = detect_signals(text)
    assert result.triggered is True

    signal_names = {s["signal"] for s in result.signals}
    assert "going_concern" in signal_names
    assert "material_weakness" in signal_names
    assert "litigation_risk" in signal_names
    assert "restatement" in signal_names

    # max severity should be going_concern at 9
    assert result.max_severity == 9

    # flags_json should be valid JSON and round-trip correctly
    parsed = json.loads(result.flags_json)
    assert len(parsed) == 4


# ── flags_json round-trip ────────────────────────────────────────────────

def test_flags_json_roundtrip():
    result = detect_signals("The company disclosed a covenant violation under its revolving credit facility.")
    parsed = json.loads(result.flags_json)
    assert len(parsed) == 1
    assert parsed[0]["signal"] == "debt_covenant_violation"
    assert parsed[0]["severity"] == 8
    assert "covenant violation" in parsed[0]["matched_text"].lower()
