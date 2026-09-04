"""
llm.py — All Gemini LLM calls, isolated from deterministic logic.

RULES:
  - Only this module calls the Gemini generative model.
  - No business logic, no database calls, no routing decisions here.
  - Inputs are plain strings/dicts. Outputs are validated Pydantic models.
  - Model fallback and rate-limit mitigation live here.
"""

import json
import re
import time
from typing import List, Optional

from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY, GEMINI_CHAT_MODELS, GEMINI_CHAT_MODEL
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

IMPORTANT: Recent tickets in the account record are HISTORY — past interactions. They do not mean the current request is automatically complex.

---
CHOOSE ONE ACTION:

ACTION: resolve  ← PREFER THIS when a KB article covers the issue
  USE WHEN: A KB article addresses the customer's issue AND you have sufficient account context.
  DO: Write a complete, specific response grounded in the KB article.
      Use the customer's real name, plan name, amounts, and dates from the account.
      Cite the KB article ID(s) used.
  EXAMPLE triggers: billing charge question, connection troubleshooting, plan info, payment query, roaming charge.

ACTION: ask  ← USE THIS when one specific piece of info is missing
  USE WHEN: You cannot resolve because one key diagnostic fact is unknown (e.g., which device, since when, wired or wifi).
  DO: Ask exactly ONE targeted question. Never ask what you already know from the account.

ACTION: escalate  ← LAST RESORT only
  USE WHEN:
    - No KB article covers the issue at all
    - The customer reports fraud, identity theft, or account hijacking
    - The issue has been attempted multiple times in THIS conversation and failed
    - The balance or charges exceed escalation thresholds stated in the KB
  DO: Write a brief, courteous message to the customer explaining the handover, AND provide a structured handover summary for the human agent.
  DO NOT escalate just because: there is an open historical ticket or you are mildly uncertain.

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
  "escalation_reason": "<one sentence reason — only if action is escalate, else null>",
  "escalation_summary": "<handover summary formatted with ISSUE:, ESTABLISHED:, TRIED:, PRIORITY: — only if action is escalate, else null>"
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
                f"  - [{t.get('ticket_id')}] {t.get('issue_type')} | "
                f"Status: {t.get('status')} | "
                f"Date: {t.get('created_at')} | "
                f"{str(t.get('description', ''))[:100]}"
            )
            if t.get("resolution"):
                line += f" | Resolution: {str(t.get('resolution'))[:80]}"
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
    Robust JSON extractor with regex fallback for unescaped characters or truncation.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Attempt 1: standard json decode
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: find first { ... } with strict=False
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        blob = match.group()
        try:
            return json.loads(blob, strict=False)
        except json.JSONDecodeError:
            pass

    # Attempt 3: Regex field extraction as graceful fallback
    extracted = {}
    act_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)
    if act_match:
        extracted["action"] = act_match.group(1)

    conf_match = re.search(r'"confidence"\s*:\s*"([^"]+)"', text)
    if conf_match:
        extracted["confidence"] = conf_match.group(1)

    resp_match = re.search(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if resp_match:
        try:
            extracted["response"] = resp_match.group(1).encode('utf-8').decode('unicode-escape')
        except Exception:
            extracted["response"] = resp_match.group(1)
    elif '"response"' in text:
        after_resp = text.split('"response"', 1)[1]
        raw_val = re.search(r':\s*"(.*?)(?:"\s*,\s*"\w+"|"\}|$)', after_resp, re.DOTALL)
        if raw_val:
            extracted["response"] = raw_val.group(1).replace('\\n', '\n')

    cite_matches = re.findall(r'ART\d{3}', text)
    if cite_matches:
        extracted["citations"] = list(dict.fromkeys(cite_matches))

    summary_match = re.search(r'"escalation_summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if summary_match:
        extracted["escalation_summary"] = summary_match.group(1).replace('\\n', '\n')

    if extracted.get("action") or extracted.get("response"):
        return extracted

    raise ValueError(f"Could not parse LLM response as JSON\nRaw: {text[:300]}")


# ── Main triage call ──────────────────────────────────────────────────────────

def triage(
    account: AccountInfo,
    messages: List[dict],
    articles: List[ArticleMatch],
) -> TriageResult:
    """
    Call Gemini to triage a customer support request.
    Includes multi-model fallback to handle rate-limits (429) or missing models (404).
    """
    client = _get_client()

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(account, messages, articles)

    raw_text = None
    last_error = None

    # Deduplicated model order starting with configured primary
    models_to_try = [GEMINI_CHAT_MODEL]
    for m in GEMINI_CHAT_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    max_output_tokens=2048,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )
            raw_text = response.text.strip()
            break
        except Exception as exc:
            err_str = str(exc).lower()
            print(f"[LLM] Model '{model_name}' encountered: {exc}. Trying fallback...")
            last_error = exc
            # Give a moment if quota / rate limit was hit
            if "429" in err_str or "resource_exhausted" in err_str:
                time.sleep(1.5)
            continue

    if raw_text is None:
        raise RuntimeError(f"All Gemini models exhausted: {last_error}") from last_error

    # Parse structured output
    try:
        data = _extract_json(raw_text)
    except ValueError as exc:
        raise RuntimeError(f"LLM returned unparseable response: {exc}") from exc

    action = data.get("action", "escalate")
    if action not in ("resolve", "ask", "escalate"):
        action = "escalate"

    confidence = data.get("confidence", "low")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

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
        escalation_summary=data.get("escalation_summary"),
    )


# ── Escalation summary builder ─────────────────────────────────────────────────

def build_escalation_summary(
    account: AccountInfo,
    messages: List[dict],
    triage_result: TriageResult,
) -> str:
    """
    Build a structured handover summary for human agents.
    If triage already generated one, use it. Otherwise, generate deterministically
    without consuming any extra API quota or risking rate-limit errors.
    """
    if triage_result.escalation_summary:
        return triage_result.escalation_summary

    last_user_turn = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"),
        "Customer assistance requested"
    )

    tried_items = []
    for m in messages:
        if m["role"] == "assistant":
            tried_items.append(m["content"][:70].replace("\n", " "))
    tried_str = "; ".join(tried_items) if tried_items else "Initial automated triage"

    priority = "Medium"
    if account.account_status != "active" or account.balance_due > 50:
        priority = "High"

    reason = triage_result.escalation_reason or "Requires human review"

    return (
        f"ISSUE: {last_user_turn[:120]}\n"
        f"ESTABLISHED: Customer {account.customer_name} (Acct: {account.account_id}), "
        f"Plan: {account.plan.name} ({account.plan.type}), Status: {account.account_status.upper()}, "
        f"Balance: Rs.{account.balance_due:.2f}. Reason: {reason}.\n"
        f"TRIED: {tried_str[:200]}\n"
        f"PRIORITY: {priority}"
    )
