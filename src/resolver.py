"""
resolver.py — Triage orchestration. The central decision engine.

This module owns the end-to-end flow for each support request:
  1. Validate account
  2. Retrieve relevant KB articles (deterministic)
  3. Call LLM triage (LLM reasoning)
  4. Post-process and return a structured ChatResponse

SEPARATION OF CONCERNS:
  - database.py  → pure data access (no LLM)
  - retrieval.py → pure vector search (no LLM)
  - llm.py       → pure LLM calls (no routing logic)
  - resolver.py  → orchestrates all three, owns routing decisions
"""

from typing import List

from src.database import get_account, get_recent_billing
from src.retrieval import search
from src.llm import triage, build_escalation_summary
from src.models import (
    AccountInfo,
    ArticleMatch,
    ChatResponse,
    Message,
    TriageResult,
)
from src.config import TOP_K_ARTICLES


# ── Query builder ─────────────────────────────────────────────────────────────

def _build_search_query(messages: List[Message]) -> str:
    """
    Build a retrieval query from the conversation.
    Uses the last 3 user messages for context (handles multi-turn conversations).
    """
    user_messages = [m.content for m in messages if m.role == "user"]
    # Take the last 3 user turns for rich context
    recent = user_messages[-3:] if len(user_messages) >= 3 else user_messages
    return " ".join(recent)


def _messages_to_dicts(messages: List[Message]) -> List[dict]:
    """Convert Pydantic Message list to plain dicts for LLM prompt building."""
    return [{"role": m.role, "content": m.content} for m in messages]


# ── Override rules (deterministic pre-LLM checks) ─────────────────────────────

def _check_deterministic_overrides(
    account: AccountInfo,
    messages: List[Message],
) -> ChatResponse | None:
    """
    Apply rule-based checks before calling the LLM.
    These handle clear-cut cases that don't need LLM reasoning.

    Returns a ChatResponse to short-circuit if a rule fires, else None.
    """
    last_user_msg = next(
        (m.content.lower() for m in reversed(messages) if m.role == "user"), ""
    )

    # Rule 1: Suspended account asking about service
    if account.account_status == "suspended":
        suspension_keywords = [
            "internet", "connection", "wifi", "wi-fi", "data", "service",
            "not working", "down", "disconnected", "slow"
        ]
        if any(kw in last_user_msg for kw in suspension_keywords):
            return ChatResponse(
                action="resolve",
                response=(
                    f"Hi {account.customer_name}, I can see your account (ID: {account.account_id}) "
                    f"is currently suspended due to an outstanding balance of "
                    f"Rs.{account.balance_due:.2f}. When an account is suspended, all broadband "
                    f"and mobile services are paused.\n\n"
                    f"To restore your services, please make a payment of Rs.{account.balance_due:.2f} "
                    f"via the MySelf app or at https://portal.nexusnow.com. "
                    f"Services typically restore within 1-4 hours after payment clears.\n\n"
                    f"If you've already paid, please share your payment confirmation and I'll "
                    f"escalate to the technical team immediately."
                ),
                citations=["ART005"],
                account_id=account.account_id,
            )

    # Rule 2: Cancelled account
    if account.account_status == "cancelled":
        return ChatResponse(
            action="escalate",
            response=(
                f"Your account (ID: {account.account_id}) shows as cancelled. "
                f"I'm connecting you with a specialist who can assist with post-cancellation queries."
            ),
            citations=[],
            account_id=account.account_id,
            escalation_summary=(
                f"ISSUE: Customer {account.customer_name} contacting on a cancelled account.\n"
                f"ESTABLISHED: Account {account.account_id} status = CANCELLED.\n"
                f"TRIED: Automated triage — no action possible on cancelled account.\n"
                f"PRIORITY: Low"
            ),
        )

    return None  # No override — proceed to LLM


# ── Main resolve function ─────────────────────────────────────────────────────

def resolve(account_id: str, messages: List[Message]) -> ChatResponse:
    """
    Process a customer support request end-to-end.

    Flow:
      1. Validate account exists
      2. Fetch account + billing context
      3. Apply deterministic override rules (suspended, cancelled, etc.)
      4. Retrieve relevant KB articles via FAISS
      5. Call Gemini LLM triage
      6. If escalating, generate structured handover summary
      7. Return ChatResponse

    All failure modes return a valid ChatResponse (never raises to the API layer).
    """

    # ── Step 1: Validate account ──────────────────────────────────────────────
    account = get_account(account_id)

    if account is None:
        return ChatResponse(
            action="ask",
            response=(
                "I wasn't able to find an account with that ID. "
                "Could you double-check your account ID? "
                "You can find it on your bill or in the MySelf app under 'My Account'."
            ),
            citations=[],
            account_id=account_id,
            error="account_not_found",
        )

    # ── Step 2: Enrich account with recent billing ───────────────────────────
    try:
        recent_billing = get_recent_billing(account_id, limit=3)
        # Attach billing history as additional context on the account object
        # (stored in recent_tickets field for simplicity — both are dicts)
        billing_note = {
            "ticket_id": "BILLING_HISTORY",
            "issue_type": "billing_history",
            "status": "info",
            "created_at": "recent",
            "description": (
                "Last 3 bills: " +
                ", ".join(
                    f"Rs.{b['amount']:.2f} ({b['status']}, due {b['due_date']})"
                    for b in recent_billing
                )
            ),
            "resolution": None,
        }
        account.recent_tickets.append(billing_note)
    except Exception:
        pass  # Non-fatal — billing history is supplementary

    # ── Step 3: Deterministic overrides ──────────────────────────────────────
    override = _check_deterministic_overrides(account, messages)
    if override is not None:
        return override

    # ── Step 4: KB article retrieval ──────────────────────────────────────────
    query = _build_search_query(messages)
    try:
        articles: List[ArticleMatch] = search(query, top_k=TOP_K_ARTICLES)
    except Exception as exc:
        print(f"[RESOLVER] Retrieval failed: {exc}")
        articles = []  # Graceful degradation → LLM will see no articles → escalate

    # ── Step 5: LLM triage ───────────────────────────────────────────────────
    messages_dicts = _messages_to_dicts(messages)

    try:
        result: TriageResult = triage(
            account=account,
            messages=messages_dicts,
            articles=articles,
        )
    except RuntimeError as exc:
        print(f"[RESOLVER] LLM triage failed: {exc}")
        # Graceful failure — produce a safe escalation without LLM
        return ChatResponse(
            action="escalate",
            response=(
                "I'm experiencing a technical issue processing your request. "
                "I'm connecting you with a human agent who will have your full account context."
            ),
            citations=[],
            account_id=account_id,
            escalation_summary=(
                f"ISSUE: Automated triage system error — customer needs manual handling.\n"
                f"ESTABLISHED: Account {account_id} | Customer: {account.customer_name} | "
                f"Plan: {account.plan.name} | Status: {account.account_status}\n"
                f"TRIED: LLM triage (failed with technical error)\n"
                f"PRIORITY: High — customer waiting, system error occurred"
            ),
            error="llm_failure",
        )

    # ── Step 6: Build escalation summary if needed ────────────────────────────
    escalation_summary = None
    if result.action == "escalate":
        try:
            escalation_summary = build_escalation_summary(
                account=account,
                messages=messages_dicts,
                triage_result=result,
            )
        except Exception as exc:
            print(f"[RESOLVER] Escalation summary generation failed: {exc}")
            # Fallback minimal summary
            escalation_summary = (
                f"ISSUE: Customer requires human assistance.\n"
                f"ESTABLISHED: {account.customer_name} | {account.account_id} | "
                f"{account.plan.name} | Status: {account.account_status}\n"
                f"TRIED: Automated triage — escalation required.\n"
                f"PRIORITY: Medium"
            )

    # ── Step 7: Return ChatResponse ───────────────────────────────────────────
    return ChatResponse(
        action=result.action,
        response=result.response,
        citations=result.citations,
        account_id=account_id,
        escalation_summary=escalation_summary,
    )
