"""
llm.py — All Gemini LLM calls, isolated from deterministic logic.

RULES:
  - Only this module calls the Gemini generative model.
  - No business logic, no database calls, no routing decisions here.
  - Inputs are plain strings/dicts. Outputs are validated Pydantic models.
  - All prompts are defined here for auditability.
"""

import json
import re
from typing import List, Optional

from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY, GEMINI_CHAT_MODEL
from src.models import AccountInfo, ArticleMatch, TriageResult


# ── Client ────────────────────────────────────────────────────────────────────

def _get_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Export it before starting the app."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return """You are a customer support resolution assistant for NexusNow, a broadband and mobile provider.
Your job is to analyse a customer support request and pick the best action: resolve, ask, or escalate.

You have three inputs:
  1. Customer's account record (plan, billing, recent ticket HISTORY)
  2. KB articles retrieved for this issue
  3. The conversation so far

IMPORTANT: Recent tickets in the account record are HISTORY — past interactions. They do not mean the current request is complex. Treat each new customer message fresh.

---
CHOOSE ONE ACTION:

ACTION: resolve  ← PREFER THIS when a KB article covers the issue
  USE WHEN: A KB article addresses the customer's issue AND you have enough account context.
  DO: Write a complete, specific response grounded in the KB article.
      Use the customer's real name, plan name, amounts, and dates from the account.
      Cite the KB article ID(s) used.
  EXAMPLE triggers: billing charge question, connection troubleshooting, plan info, payment query, roaming charge.

ACTION: ask  ← USE THIS when one specific piece of info is missing
  USE WHEN: You cannot resolve because one key fact is unknown (e.g., which device, since when, wired or wifi).
  DO: Ask exactly ONE targeted question. Never ask what you already know from the account.

ACTION: escalate  ← LAST RESORT only
  USE WHEN:
    - No KB article covers the issue at all
    - The customer reports fraud, identity theft, or account hijacking
    - The issue has been attempted multiple times in THIS conversation and failed
    - The balance or charges exceed escalation thresholds stated in the KB
  DO: Write a brief escalation note to the customer AND a structured handover summary.
  DO NOT escalate just because: there is an open historical ticket, the issue seems complex, or you are mildly uncertain.

---
RULES:
  - Prefer resolve over escalate whenever a KB article is relevant
  - Never fabricate policy, numbers, or procedures not in the KB
  - Citations must be article IDs from the articles actually provided to you
  - Respond in valid JSON only — no text outside the JSON object

RESPONSE FORMAT (JSON only, no markdown fences):
{
  "action": "resolve" | "ask" | "escalate",
  "confidence": "high" | "medium" | "low",
  "response": "<the full response text — grounded, specific, professional>",
  "citations": ["ART001"],
  "missing_info": "<what is missing — only if action is ask, else null>",
  "escalation_reason": "<one sentence reason — only if action is escalate, else null>"
}"""



def _build_user_prompt(
    account: AccountInfo,
    messages: List[dict],
    articles: List[ArticleMatch],
) -> str:
    """Assemble the full user-turn prompt with account context + KB articles."""

    # ── Account context block ─────────────────────────────────────────────────
    billing_status = (
        f"OVERDUE - balance of Rs.{account.balance_due:.2f}"
        if account.balance_due > 0
        else "clear"
    )

    recent_tickets_text = ""
    if account.recent_tickets:
        ticket_lines = []
        for t in account.recent_tickets[:3]:
            line = (
                f"  - [{t['ticket_id']}] {t['issue_type']} | "
                f"Status: {t['status']} | "
                f"Date: {t['created_at']} | "
                f"{t['description'][:100]}"
            )
            if t.get("resolution"):
                line += f" | Resolution: {t['resolution'][:80]}"
            ticket_lines.append(line)
        recent_tickets_text = "\n".join(ticket_lines)
    else:
        recent_tickets_text = "  None"

    plan = account.plan
    plan_details = f"{plan.name} ({plan.type})"
    if plan.speed_mbps:
        plan_details += f" | {plan.speed_mbps} Mbps"
    if plan.data_gb:
        plan_details += f" | {plan.data_gb} GB data"
    plan_details += f" | Rs.{plan.monthly_cost:.2f}/month"

    account_block = f"""=== CUSTOMER ACCOUNT ===
Account ID    : {account.account_id}
Customer      : {account.customer_name}
Email         : {account.email}
Phone         : {account.phone}
Plan          : {plan_details}
Account Status: {account.account_status.upper()}
Next Bill Date: {account.billing_due_date}
Billing Status: {billing_status}

Recent Support Tickets:
{recent_tickets_text}"""

    # ── KB articles block ─────────────────────────────────────────────────────
    if articles:
        article_lines = []
        for art in articles:
            article_lines.append(
                f"\n--- [{art.article_id}] {art.title} (relevance: {art.score}) ---\n"
                f"{art.content}\n"
                f"--- END {art.article_id} ---"
            )
        articles_block = "=== KNOWLEDGE BASE ARTICLES ===\n" + "\n".join(article_lines)
    else:
        articles_block = (
            "=== KNOWLEDGE BASE ARTICLES ===\n"
            "No relevant articles found for this query.\n"
            "You must escalate — do not attempt to resolve without KB grounding."
        )

    # ── Conversation block ────────────────────────────────────────────────────
    conv_lines = []
    for msg in messages:
        role_label = "CUSTOMER" if msg["role"] == "user" else "AGENT"
        conv_lines.append(f"{role_label}: {msg['content']}")
    conversation_block = "=== CONVERSATION ===\n" + "\n".join(conv_lines)

    return f"""{account_block}

{articles_block}

{conversation_block}

=== YOUR TASK ===
Analyse the conversation, account details, and KB articles above.
Determine the correct action (resolve / ask / escalate) and respond in valid JSON only."""


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract JSON from the LLM response.
    Handles markdown code blocks and bare JSON robustly.
    """
    # Strip markdown code fences if present
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Try to find first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse LLM response as JSON: {exc}\nRaw: {text[:300]}")


# ── Main triage call ──────────────────────────────────────────────────────────

def triage(
    account: AccountInfo,
    messages: List[dict],
    articles: List[ArticleMatch],
) -> TriageResult:
    """
    Call Gemini to triage a customer support request.

    Args:
        account  : Full customer account context
        messages : Conversation history [{"role": "user"|"assistant", "content": "..."}]
        articles : Retrieved KB articles (may be empty)

    Returns:
        TriageResult with action, confidence, response, citations

    Raises:
        RuntimeError on unrecoverable LLM failure (caller should escalate gracefully)
    """
    client = _get_client()

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(account, messages, articles)

    try:
        response = client.models.generate_content(
            model=GEMINI_CHAT_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,        # Low temp for consistent, grounded responses
                max_output_tokens=1024,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True         # Suppress AFC warning — we don't use tools
                ),
            ),
        )

        raw_text = response.text.strip()

    except Exception as exc:
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    # Parse and validate the structured output
    try:
        data = _extract_json(raw_text)
    except ValueError as exc:
        raise RuntimeError(f"LLM returned unparseable response: {exc}") from exc

    # Validate action
    action = data.get("action", "escalate")
    if action not in ("resolve", "ask", "escalate"):
        action = "escalate"

    # Validate confidence
    confidence = data.get("confidence", "low")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    # Validate citations — only include IDs that were actually provided
    valid_article_ids = {a.article_id for a in articles}
    raw_citations = data.get("citations", [])
    if isinstance(raw_citations, list):
        citations = [c for c in raw_citations if c in valid_article_ids]
    else:
        citations = []

    return TriageResult(
        action=action,
        confidence=confidence,
        response=data.get("response", "I'm unable to process this request right now."),
        citations=citations,
        missing_info=data.get("missing_info"),
        escalation_reason=data.get("escalation_reason"),
    )


# ── Escalation summary builder ─────────────────────────────────────────────────

def build_escalation_summary(
    account: AccountInfo,
    messages: List[dict],
    triage_result: TriageResult,
) -> str:
    """
    Build a structured handover summary for human agents.
    Called when action == escalate, to give the human agent full context.
    """
    client = _get_client()

    conv_text = "\n".join(
        f"{'CUSTOMER' if m['role'] == 'user' else 'AGENT'}: {m['content']}"
        for m in messages
    )

    prompt = f"""Create a brief, structured handover summary for a human support agent.

Customer: {account.customer_name} | Account: {account.account_id}
Plan: {account.plan.name} | Status: {account.account_status}

Conversation:
{conv_text}

Escalation reason: {triage_result.escalation_reason or 'Complex case requiring human review'}

Write the summary in this exact format:
ISSUE: <one sentence describing what the customer needs>
ESTABLISHED: <bullet points of what is confirmed/known>
TRIED: <what has already been attempted in this conversation, or None>
PRIORITY: <Low / Medium / High based on account status and issue severity>"""

    try:
        response = client.models.generate_content(
            model=GEMINI_CHAT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=400,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )
        return response.text.strip()
    except Exception as exc:
        # Fallback — build a minimal summary without LLM
        return (
            f"ISSUE: Customer {account.customer_name} requires human assistance.\n"
            f"ESTABLISHED: Account {account.account_id} on {account.plan.name} plan.\n"
            f"TRIED: Automated triage attempted.\n"
            f"PRIORITY: Medium\n"
            f"NOTE: LLM summary generation failed — {exc}"
        )
