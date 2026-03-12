"""Flask web UI for Redline SEC filing change detection tool.

Routes:
  /                  Dashboard: diffs only, color-coded scores, filter by ticker
  /company/<ticker>  All filings with extraction badges per section
  /diff/<diff_id>    Diff detail with colored diff, LLM analysis, sibling extractions
  /watchlist         CRUD via watchlist.py module
"""

from flask import Flask, render_template, request, redirect, url_for, flash
from redline import storage, watchlist

app = Flask(__name__)
app.secret_key = "redline-dev-key"


@app.template_filter("score_class")
def score_class_filter(score):
    """Return CSS class name for a given score value."""
    if score is None:
        return "score-none"
    score = int(score)
    if score <= 3:
        return "score-low"
    elif score <= 6:
        return "score-mid"
    else:
        return "score-high"


@app.template_filter("pct")
def pct_filter(value):
    """Format a float as a percentage string."""
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


@app.template_filter("extraction_class")
def extraction_class_filter(status):
    """Return CSS class for extraction badge."""
    if status == "success":
        return "badge-success"
    elif status == "failed":
        return "badge-failed"
    else:
        return "badge-notfound"


@app.route("/")
def dashboard():
    """Dashboard: diffs only, color-coded scores, filter by ticker."""
    ticker_filter = request.args.get("ticker", "").strip()
    if ticker_filter:
        diffs = storage.get_diffs_for_ticker(ticker_filter)
    else:
        diffs = storage.get_all_diffs(limit=100)
    tickers = watchlist.list_tickers()
    return render_template("dashboard.html", diffs=diffs, tickers=tickers,
                           current_ticker=ticker_filter)


@app.route("/company/<ticker>")
def company(ticker):
    """Company page: all filings with extraction badges."""
    filings = storage.get_filings_for_ticker(ticker)
    for f in filings:
        f["extractions"] = storage.get_extraction_attempts(f["id"])
    return render_template("company.html", ticker=ticker, filings=filings)


@app.route("/diff/<diff_id>")
def diff_detail(diff_id):
    """Diff detail with colored diff, LLM analysis, sibling extractions."""
    diff = storage.get_diff_by_id(diff_id)
    if not diff:
        return "Diff not found", 404
    extractions = storage.get_extraction_attempts(diff["filing_id"])
    return render_template("diff_detail.html", diff=diff, extractions=extractions)


@app.route("/watchlist", methods=["GET", "POST"])
def watchlist_page():
    """Watchlist management."""
    if request.method == "POST":
        action = request.form.get("action")
        ticker = request.form.get("ticker", "").strip()
        if action == "add" and ticker:
            if not watchlist.validate_ticker(ticker):
                flash(f"Invalid ticker: {ticker}", "error")
            elif watchlist.add_ticker(ticker):
                flash(f"Added {ticker.upper()}", "success")
            else:
                flash(f"{ticker.upper()} already in watchlist", "warning")
        elif action == "remove" and ticker:
            if watchlist.remove_ticker(ticker):
                flash(f"Removed {ticker.upper()}", "success")
            else:
                flash(f"{ticker.upper()} not found in watchlist", "warning")
        return redirect(url_for("watchlist_page"))

    tickers = watchlist.list_tickers()
    return render_template("watchlist.html", tickers=tickers)


if __name__ == "__main__":
    storage.init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
