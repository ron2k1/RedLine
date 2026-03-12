import json
import os
import re
import tempfile

from redline import config

TICKER_PATTERN = re.compile(r'^[A-Z]{1,5}([.\-][A-Z]{1,2})?$')


def normalize_ticker(ticker: str) -> str:
    """Uppercase, replace '.' with '-' to match SEC canonical form."""
    return ticker.upper().strip().replace('.', '-')


def validate_ticker(ticker: str) -> bool:
    """Accepts BRK.B, BRK-B, AAPL, etc."""
    return bool(TICKER_PATTERN.match(ticker.upper().strip()))


def _watchlist_path() -> str:
    return config.WATCHLIST_PATH


def load() -> dict:
    """Load watchlist from JSON file."""
    path = _watchlist_path()
    if not os.path.exists(path):
        return {"tickers": [], "form_types": ["10-K", "10-Q"],
                "sections": ["1A", "7", "3", "9A"]}
    with open(path, "r") as f:
        return json.load(f)


def save(data: dict) -> None:
    """Atomic write: write to temp file then rename."""
    path = _watchlist_path()
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        # On Windows, os.replace is atomic
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def add_ticker(ticker: str) -> bool:
    """Add ticker to watchlist. Returns True if added, False if already present or invalid."""
    if not validate_ticker(ticker):
        return False
    normalized = normalize_ticker(ticker)
    data = load()
    if normalized in data["tickers"]:
        return False
    data["tickers"].append(normalized)
    save(data)
    return True


def remove_ticker(ticker: str) -> bool:
    """Remove ticker from watchlist. Returns True if removed, False if not found."""
    normalized = normalize_ticker(ticker)
    data = load()
    if normalized not in data["tickers"]:
        return False
    data["tickers"].remove(normalized)
    save(data)
    return True


def list_tickers() -> list[str]:
    """Return list of tickers in watchlist."""
    return load()["tickers"]
