import json
import os
import tempfile
import pytest
from redline import watchlist, config


@pytest.fixture(autouse=True)
def tmp_watchlist(monkeypatch):
    """Use a temp file for watchlist during tests."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    monkeypatch.setattr(config, "WATCHLIST_PATH", path)
    with open(path, "w") as f:
        json.dump({"tickers": [], "form_types": ["10-K", "10-Q"],
                    "sections": ["1A", "7", "3", "9A"]}, f)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_add_ticker():
    assert watchlist.add_ticker("AAPL") is True
    assert "AAPL" in watchlist.list_tickers()


def test_add_duplicate_rejected():
    watchlist.add_ticker("AAPL")
    assert watchlist.add_ticker("AAPL") is False
    assert watchlist.list_tickers().count("AAPL") == 1


def test_remove_ticker():
    watchlist.add_ticker("MSFT")
    assert watchlist.remove_ticker("MSFT") is True
    assert "MSFT" not in watchlist.list_tickers()


def test_remove_nonexistent():
    assert watchlist.remove_ticker("ZZZZ") is False


def test_list_tickers():
    watchlist.add_ticker("AAPL")
    watchlist.add_ticker("TSLA")
    tickers = watchlist.list_tickers()
    assert "AAPL" in tickers
    assert "TSLA" in tickers


def test_normalize_brk_b():
    """BRK.B should be stored as BRK-B."""
    watchlist.add_ticker("BRK.B")
    assert "BRK-B" in watchlist.list_tickers()
    assert "BRK.B" not in watchlist.list_tickers()


def test_normalize_lowercase():
    watchlist.add_ticker("aapl")
    assert "AAPL" in watchlist.list_tickers()


def test_validate_ticker_valid():
    assert watchlist.validate_ticker("AAPL") is True
    assert watchlist.validate_ticker("BRK.B") is True
    assert watchlist.validate_ticker("BRK-B") is True
    assert watchlist.validate_ticker("BF.A") is True


def test_validate_ticker_invalid():
    assert watchlist.validate_ticker("") is False
    assert watchlist.validate_ticker("TOOLONGTICKER") is False
    assert watchlist.validate_ticker("123") is False


def test_atomic_write(tmp_watchlist):
    """Verify file is valid JSON after write."""
    watchlist.add_ticker("NVDA")
    with open(tmp_watchlist, "r") as f:
        data = json.load(f)
    assert "NVDA" in data["tickers"]


def test_load_missing_file(monkeypatch):
    """Loading a non-existent file returns defaults."""
    monkeypatch.setattr(config, "WATCHLIST_PATH", "/tmp/nonexistent_watchlist_test.json")
    data = watchlist.load()
    assert data["tickers"] == []
    assert "10-K" in data["form_types"]
