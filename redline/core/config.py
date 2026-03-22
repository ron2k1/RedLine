import os
from dotenv import load_dotenv

load_dotenv()

SEC_USER_AGENT: str = os.getenv("SEC_USER_AGENT", "")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
DB_PATH: str = os.getenv("DB_PATH", "./redline.db")
WATCHLIST_PATH: str = os.getenv("WATCHLIST_PATH", "./watchlist.json")
MIN_PCT_CHANGED: float = float(os.getenv("MIN_PCT_CHANGED", "0.05"))
PRELIMINARY_SCORE_LLM_THRESHOLD: int = int(os.getenv("PRELIMINARY_SCORE_LLM_THRESHOLD", "4"))
BACKFILL_YEARS: int = int(os.getenv("BACKFILL_YEARS", "5"))

# --- Semantic diff settings ---
# Model: 'all-MiniLM-L6-v2' (~80MB, fast CPU) or 'BAAI/bge-large-en-v1.5' (~1.3GB, more accurate)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
SEMANTIC_DIFF_ENABLED: bool = os.getenv("SEMANTIC_DIFF_ENABLED", "true").lower() == "true"
# Thresholds: sentences above UNCHANGED are "same meaning"; between CHANGED and UNCHANGED are "modified";
# below CHANGED are "completely different" (added/deleted). Tune against real filings.
SEMANTIC_UNCHANGED_THRESHOLD: float = float(os.getenv("SEMANTIC_UNCHANGED_THRESHOLD", "0.85"))
SEMANTIC_CHANGED_THRESHOLD: float = float(os.getenv("SEMANTIC_CHANGED_THRESHOLD", "0.55"))
EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
# Store section embeddings for anomaly detection.
STORE_EMBEDDINGS: bool = os.getenv("STORE_EMBEDDINGS", "true").lower() == "true"

# --- Anomaly detection settings ---
ANOMALY_DETECTION_ENABLED: bool = os.getenv("ANOMALY_DETECTION_ENABLED", "true").lower() == "true"
ANOMALY_MIN_HISTORY: int = int(os.getenv("ANOMALY_MIN_HISTORY", "3"))
ANOMALY_Z_THRESHOLD: float = float(os.getenv("ANOMALY_Z_THRESHOLD", "2.0"))

# --- Scheduler settings ---
POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
MARKET_OPEN_HOUR: int = int(os.getenv("MARKET_OPEN_HOUR", "9"))
MARKET_OPEN_MINUTE: int = int(os.getenv("MARKET_OPEN_MINUTE", "30"))
MARKET_CLOSE_HOUR: int = int(os.getenv("MARKET_CLOSE_HOUR", "16"))
MARKET_CLOSE_MINUTE: int = int(os.getenv("MARKET_CLOSE_MINUTE", "0"))
ALERT_SCORE_THRESHOLD: int = int(os.getenv("ALERT_SCORE_THRESHOLD", "7"))
ALERTS_PATH: str = os.getenv("ALERTS_PATH", "./alerts/alerts.jsonl")
