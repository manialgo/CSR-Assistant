"""
retrieval.py — FAISS-based KB article retrieval using Gemini embeddings.

DETERMINISTIC LAYER — No LLM reasoning here.
This module embeds text, indexes articles, and returns ranked matches.
All LLM calls live in llm.py.
"""

import json
import time
import numpy as np
import faiss
from pathlib import Path
from typing import List, Optional, Tuple

from google import genai

from src.config import (
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    ARTICLES_DIR,
    FAISS_INDEX_PATH,
    ARTICLE_METADATA_PATH,
    TOP_K_ARTICLES,
    SIMILARITY_THRESHOLD,
)
from src.models import ArticleMatch


# ── Module-level cache (loaded once at startup) ───────────────────────────────
_faiss_index: Optional[faiss.Index] = None
_article_metadata: Optional[List[dict]] = None


def _get_client() -> genai.Client:
    """Return a Gemini client. Raises clearly if key is missing."""
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set. "
            "Export it before starting the application."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def _embed_text(client: genai.Client, text: str) -> List[float]:
    """
    Embed a single text string using Gemini embedding model.
    Returns a list of floats (the embedding vector).
    Retries once on transient failure with a 2-second backoff.
    """
    for attempt in range(2):
        try:
            response = client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=text,
            )
            return response.embeddings[0].values
        except Exception as exc:
            if attempt == 0:
                print(f"[RETRIEVAL] Embed attempt 1 failed ({exc}), retrying in 2s...")
                time.sleep(2)
            else:
                raise RuntimeError(
                    f"Embedding failed after 2 attempts: {exc}"
                ) from exc


def _parse_article_header(content: str, filepath: Path) -> Tuple[str, str]:
    """
    Extract article_id and title from article markdown.
    Falls back to filename-based defaults if headers are missing.
    """
    article_id = filepath.stem.split("_")[0]  # ART001_billing_disputes → ART001
    title = filepath.stem

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and title == filepath.stem:
            title = line[2:].strip()
        if "**Article ID:**" in line:
            parts = line.split("**Article ID:**")
            if len(parts) > 1:
                article_id = parts[1].strip()

    return article_id, title


# ── Index build ───────────────────────────────────────────────────────────────

def build_index() -> None:
    """
    Read all KB articles, generate Gemini embeddings, build FAISS index,
    and persist both index and metadata to disk.

    Called by scripts/build_index.py to pre-build the committed index.
    Also called at app startup automatically if index file is missing.
    """
    client = _get_client()

    article_files = sorted(ARTICLES_DIR.glob("*.md"))
    if not article_files:
        raise FileNotFoundError(
            f"No .md files found in {ARTICLES_DIR}. "
            "Ensure data/articles/ contains KB markdown articles."
        )

    print(f"[RETRIEVAL] Embedding {len(article_files)} articles...")

    articles: List[dict] = []
    all_vectors: List[List[float]] = []

    for filepath in article_files:
        content = filepath.read_text(encoding="utf-8")
        article_id, title = _parse_article_header(content, filepath)

        # Embed title + full article body for rich semantic coverage
        embed_input = f"{title}\n\n{content}"

        print(f"  → [{article_id}] {title}")
        vector = _embed_text(client, embed_input)

        articles.append({
            "article_id": article_id,
            "title": title,
            "filepath": str(filepath.resolve()),
            "content": content,
        })
        all_vectors.append(vector)

        time.sleep(0.3)  # Respect Gemini API rate limits

    # Build FAISS IndexFlatIP (cosine similarity on L2-normalised vectors)
    dim = len(all_vectors[0])
    matrix = np.array(all_vectors, dtype=np.float32)
    faiss.normalize_L2(matrix)  # In-place normalisation

    index = faiss.IndexFlatIP(dim)
    index.add(matrix)

    # Persist
    FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))

    with open(ARTICLE_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    print(f"[RETRIEVAL] OK FAISS index : {len(articles)} vectors, dim={dim}")
    print(f"[RETRIEVAL] OK Index saved : {FAISS_INDEX_PATH}")
    print(f"[RETRIEVAL] OK Metadata    : {ARTICLE_METADATA_PATH}")


# ── Load into memory at startup ───────────────────────────────────────────────

def load_index() -> None:
    """
    Load the pre-built FAISS index and article metadata into module-level cache.
    Must be called once at application startup before any search() calls.
    Automatically builds the index if not found on disk.
    """
    global _faiss_index, _article_metadata

    if not FAISS_INDEX_PATH.exists() or not ARTICLE_METADATA_PATH.exists():
        print("[RETRIEVAL] Pre-built index not found — building now (~30s)...")
        build_index()

    _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))

    with open(ARTICLE_METADATA_PATH, "r", encoding="utf-8") as f:
        _article_metadata = json.load(f)

    print(
        f"[RETRIEVAL] OK Loaded: {_faiss_index.ntotal} articles, "
        f"dim={_faiss_index.d}"
    )


# ── Search ────────────────────────────────────────────────────────────────────

def search(query: str, top_k: int = TOP_K_ARTICLES) -> List[ArticleMatch]:
    """
    Retrieve the most relevant KB articles for a given query string.

    Args:
        query : Customer issue or question (free text)
        top_k : Maximum results to return

    Returns:
        List[ArticleMatch] sorted by descending similarity score.
        Returns [] if no articles meet SIMILARITY_THRESHOLD.
        The resolver interprets an empty list as "no KB coverage" → escalate.
    """
    if _faiss_index is None or _article_metadata is None:
        raise RuntimeError(
            "Retrieval index not loaded. Call load_index() at application startup."
        )

    client = _get_client()

    # Embed the query
    try:
        query_vec = np.array([_embed_text(client, query)], dtype=np.float32)
    except Exception as exc:
        print(f"[RETRIEVAL] Query embedding failed: {exc}")
        return []  # Graceful degradation — resolver will escalate

    faiss.normalize_L2(query_vec)

    # Search
    k = min(top_k, _faiss_index.ntotal)
    scores, indices = _faiss_index.search(query_vec, k)

    results: List[ArticleMatch] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue  # FAISS padding for small indices
        if float(score) < SIMILARITY_THRESHOLD:
            continue  # Not relevant enough

        art = _article_metadata[int(idx)]
        results.append(
            ArticleMatch(
                article_id=art["article_id"],
                title=art["title"],
                content=art["content"],
                score=round(float(score), 4),
            )
        )

    return results


def is_index_loaded() -> bool:
    """True if the index is in memory and ready to serve queries."""
    return _faiss_index is not None and _article_metadata is not None
