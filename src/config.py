"""
config.py — Central configuration and constants.
All environment-dependent values live here; nothing else reads os.environ directly.
"""

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ARTICLES_DIR = DATA_DIR / "articles"
DB_PATH = DATA_DIR / "accounts.db"
FAISS_INDEX_PATH = DATA_DIR / "faiss.index"
ARTICLE_METADATA_PATH = DATA_DIR / "article_metadata.json"
FRONTEND_DIR = BASE_DIR / "frontend"

# ── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Supported Gemini models with automatic fallback if quota/availability issues occur:
GEMINI_CHAT_MODELS = [
    os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash-lite"),
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
]
GEMINI_CHAT_MODEL = GEMINI_CHAT_MODELS[0]
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"

# ── Retrieval ────────────────────────────────────────────────────────────────
TOP_K_ARTICLES = 3           # Number of KB articles to retrieve per query
SIMILARITY_THRESHOLD = 0.45  # Cosine similarity cutoff — tuned for 8-article KB

# ── Triage thresholds ────────────────────────────────────────────────────────
# Confidence returned by LLM triage step drives routing:
#   HIGH   → draft resolution
#   MEDIUM → ask clarifying question
#   LOW    → escalate to human
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

# ── Server ───────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8000
