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
