"""Tests for redline.signals — pattern signal detector."""

import json

from redline.analysis.signals import detect_signals


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


def test_going_concern_raised_variant():
    result = detect_signals("These conditions raised substantial doubt about our ability to continue.")
    match = [s for s in result.signals if s["signal"] == "going_concern"]
    assert len(match) == 1


def test_going_concern_no_partial_match():
    """'ongoing concerns' should not trigger going_concern."""
    result = detect_signals("Management addressed several ongoing concerns about supply chain delays.")
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


def test_auditor_change_principal_resigned():
    result = detect_signals("On March 15, the principal accountant resigned effective immediately.")
    match = [s for s in result.signals if s["signal"] == "auditor_change"]
    assert len(match) == 1


def test_auditor_change_dismissed_accounting_firm():
    result = detect_signals("The registrant dismissed its independent registered public accounting firm.")
    match = [s for s in result.signals if s["signal"] == "auditor_change"]
    assert len(match) == 1


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


def test_restatement_previously_issued():
    result = detect_signals("The audit committee approved a restatement of previously issued financial statements.")
    match = [s for s in result.signals if s["signal"] == "restatement"]
    assert len(match) == 1


def test_restatement_correcting_error():
    result = detect_signals("Management is correcting an error in previously reported financial results.")
    match = [s for s in result.signals if s["signal"] == "restatement"]
    assert len(match) == 1


def test_restatement_no_false_positive_on_general_correction():
    """'correcting an error' without financial context should not trigger."""
    result = detect_signals("The team is correcting an error in the website layout.")
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


def test_material_weaknesses_plural():
    result = detect_signals("The company disclosed two material weaknesses in its 10-K filing.")
    match = [s for s in result.signals if s["signal"] == "material_weakness"]
    assert len(match) == 1


def test_significant_deficiencies_plural():
    result = detect_signals("Auditors noted significant deficiencies in internal control procedures.")
    match = [s for s in result.signals if s["signal"] == "material_weakness"]
    assert len(match) == 1


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


def test_goodwill_write_down_hyphenated():
    result = detect_signals("The segment reported a $50M goodwill write-down in Q4.")
    match = [s for s in result.signals if s["signal"] == "goodwill_impairment"]
    assert len(match) == 1


def test_goodwill_write_down_no_hyphen():
    result = detect_signals("The segment reported a $50M goodwill writedown in Q4.")
    match = [s for s in result.signals if s["signal"] == "goodwill_impairment"]
    assert len(match) == 1


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


def test_revenue_recognition_revised_policy():
    result = detect_signals("Management revised its revenue recognition policies effective January 1.")
    match = [s for s in result.signals if s["signal"] == "revenue_recognition_change"]
    assert len(match) == 1


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


def test_debt_covenant_default_under_credit_agreement():
    result = detect_signals("The company was in default under the credit agreement dated March 2024.")
    match = [s for s in result.signals if s["signal"] == "debt_covenant_violation"]
    assert len(match) == 1


def test_debt_covenant_noncompliance_no_hyphen():
    result = detect_signals("The borrower reported noncompliance with its debt obligations.")
    match = [s for s in result.signals if s["signal"] == "debt_covenant_violation"]
    assert len(match) == 1


def test_debt_covenant_waiver_obtained():
    result = detect_signals("A waiver was obtained from the lender for the fiscal Q3 violation.")
    match = [s for s in result.signals if s["signal"] == "debt_covenant_violation"]
    assert len(match) == 1


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


def test_related_party_no_hyphen():
    result = detect_signals("The board approved a related party transaction valued at $10 million.")
    match = [s for s in result.signals if s["signal"] == "related_party_transaction"]
    assert len(match) == 1


def test_related_parties_plural():
    result = detect_signals("Certain transactions with related parties were disclosed in Note 15.")
    match = [s for s in result.signals if s["signal"] == "related_party_transaction"]
    assert len(match) == 1


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


def test_litigation_class_action_hyphenated():
    result = detect_signals("A class-action complaint was filed in the Southern District of New York.")
    match = [s for s in result.signals if s["signal"] == "litigation_risk"]
    assert len(match) == 1


def test_litigation_material_litigation():
    result = detect_signals("The company faces material litigation that could impact operations.")
    match = [s for s in result.signals if s["signal"] == "litigation_risk"]
    assert len(match) == 1


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
