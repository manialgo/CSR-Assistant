"""
scripts/test_resolver.py — End-to-end triage test covering all 3 paths.

Run with GEMINI_API_KEY set:
    python scripts/test_resolver.py

Tests:
  1. RESOLVE  — billing duplicate charge (routine, article exists)
  2. ASK      — vague connection complaint (missing info)
  3. ESCALATE — suspended account connection query (deterministic override)
  4. ESCALATE — out-of-scope query (no KB article match)
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval import load_index
from src.resolver import resolve
from src.models import Message


def print_result(test_name: str, result):
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")
    print(f"ACTION     : {result.action.upper()}")
    print(f"ACCOUNT ID : {result.account_id}")
    print(f"CITATIONS  : {result.citations}")
    if result.error:
        print(f"ERROR      : {result.error}")
    print(f"\nRESPONSE:\n{result.response}")
    if result.escalation_summary:
        print(f"\nHANDOVER SUMMARY:\n{result.escalation_summary}")
    print()


def main():
    print("Loading FAISS index...")
    load_index()
    print("Index loaded. Running tests...\n")

    import time

    # ── Test 1: Billing dispute → grounded in ART001 ─────────────────────────
    result1 = resolve(
        account_id="ACC009",
        messages=[
            Message(role="user", content=(
                "Hi, my bill this month is Rs.200 more than last month "
                "but I haven't changed my plan. Can you explain this charge?"
            ))
        ]
    )
    print_result("Billing Dispute — Grounded in ART001", result1)
    time.sleep(1.5)

    # ── Test 2: Vague connection issue → should ASK ──────────────────────────
    result2 = resolve(
        account_id="ACC001",
        messages=[
            Message(role="user", content="My internet isn't working.")
        ]
    )
    print_result("Vague Connection Issue — Expect: ASK for more info", result2)
    time.sleep(1.5)

    # ── Test 3: Suspended account, asks about connection → DETERMINISTIC RESOLVE
    result3 = resolve(
        account_id="ACC004",
        messages=[
            Message(role="user", content="My internet is not working, please help.")
        ]
    )
    print_result("Suspended Account — Expect: RESOLVE (deterministic override)", result3)
    time.sleep(1.5)

    # ── Test 4: Roaming charge dispute → should RESOLVE with ART004 ──────────
    result4 = resolve(
        account_id="ACC005",
        messages=[
            Message(role="user", content=(
                "I travelled to UAE last week and came back with a Rs.1200 roaming "
                "charge. I had no idea roaming would cost this much. Can this be reversed?"
            ))
        ]
    )
    print_result("Roaming Charge Dispute — Expect: RESOLVE with ART004 citation", result4)
    time.sleep(1.5)

    # ── Test 5: Out of scope → should ESCALATE ───────────────────────────────
    result5 = resolve(
        account_id="ACC001",
        messages=[
            Message(role="user", content=(
                "I want to know if you offer business leased lines "
                "with guaranteed 10 Gbps symmetric speeds and SLA under 15 minutes."
            ))
        ]
    )
    print_result("Out-of-scope Enterprise Query — Expect: ESCALATE", result5)

    print("All tests complete.")


if __name__ == "__main__":
    main()
