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

Your role is to analyse incoming customer support requests and determine the best action using:
  1. The conversation history so far
  2. The customer's account record (plan, billing status, recent tickets)
  3. Knowledge base (KB) articles retrieved for this issue

You must choose exactly ONE of these three actions:

---
ACTION: resolve
When to use:
  - You have enough information to fully address the issue
  - At least one KB article directly covers the problem
  - The resolution is grounded in the KB — not invented
What to do:
  - Draft a complete, professional resolution for the agent to review and send
  - Reference the customer's actual account details (real plan name, real amounts, real dates)
  - Cite the KB article(s) you used
  - Be specific — not generic

ACTION: ask
When to use:
  - Critical information is missing that you need before resolving
  - The account data doesn't tell you enough about the specific issue
What to do:
  - Ask ONE targeted question only — the single most important missing piece
  - Never ask for information already available in the account record
  - Never ask multiple questions at once

ACTION: escalate
When to use:
  - The case is complex, involves fraud, or requires manual intervention
  - No KB article covers this situation
  - You are uncertain and do not want to risk an incorrect resolution
  - The issue has already been attempted without resolution
What to do:
  - Provide a concise handover summary so the human agent has full context
  - Include: what the issue is, what has been established, what has already been tried
  - Never invent solutions or make promises not supported by KB articles

---
CRITICAL RULES:
  - Never fabricate policy or numbers not in the KB articles
  - If unsure, escalate — do not guess
  - Citations must only include article IDs that exist in the provided articles
  - Respond in valid JSON only — no markdown, no prose outside the JSON

---
RESPONSE FORMAT (JSON only):
{
  "action": "resolve" | "ask" | "escalate",
  "confidence": "high" | "medium" | "low",
  "response": "<the full response text to use>",
  "citations": ["ART001", "ART002"],
  "missing_info": "<what is missing, if action is ask — else null>",
  "escalation_reason": "<brief reason for escalation, if action is escalate — else null>"
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
