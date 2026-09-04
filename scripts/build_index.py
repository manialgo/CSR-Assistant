"""
scripts/build_index.py — Pre-build the FAISS index and commit it to the repo.

Run this script ONCE before submission:
    python scripts/build_index.py

This generates:
    data/faiss.index         ← FAISS binary index
    data/article_metadata.json ← Article content + metadata

Pre-committing the index ensures app.py starts within the 90-second limit
without needing to generate embeddings at judge runtime.

Requirements:
    GEMINI_API_KEY must be set in the environment.
"""

import sys
import os
from pathlib import Path

# Make src importable from the scripts/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval import build_index
from src.config import FAISS_INDEX_PATH, ARTICLE_METADATA_PATH, GEMINI_API_KEY


def main():
    print("=" * 60)
    print("CSR Assistant — KB Index Builder")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("\n[ERROR] GEMINI_API_KEY is not set.")
        print("Run: export GEMINI_API_KEY=your-key-here")
        sys.exit(1)

    print(f"\nIndex output  : {FAISS_INDEX_PATH}")
    print(f"Metadata output: {ARTICLE_METADATA_PATH}")
    print()

    try:
        build_index()
        print()
        print("=" * 60)
        print("OK Index built successfully. Commit these files:")
        print(f"  {FAISS_INDEX_PATH}")
        print(f"  {ARTICLE_METADATA_PATH}")
        print("=" * 60)
    except Exception as e:
        print(f"\n[ERROR] Index build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
