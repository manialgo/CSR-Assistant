"""
models.py — Pydantic schemas for all request/response contracts.
LLM outputs and API payloads are validated here before use elsewhere.
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ── Inbound ──────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    account_id: str = Field(..., description="Customer account ID")
    messages: List[Message] = Field(..., description="Full conversation history")


# ── Account / Ticket data ─────────────────────────────────────────────────────

class PlanInfo(BaseModel):
    plan_id: str
    name: str
    type: Literal["broadband", "mobile", "bundle"]
    speed_mbps: Optional[int] = None
    data_gb: Optional[int] = None
    monthly_cost: float


class AccountInfo(BaseModel):
    account_id: str
    customer_name: str
    email: str
    phone: str
    plan: PlanInfo
    account_status: Literal["active", "suspended", "cancelled"]
    billing_due_date: str
    balance_due: float
    recent_tickets: List[dict] = []


# ── Retrieved article ─────────────────────────────────────────────────────────

class ArticleMatch(BaseModel):
    article_id: str
    title: str
    content: str
    score: float


# ── LLM triage output ────────────────────────────────────────────────────────

class TriageResult(BaseModel):
    action: Literal["resolve", "ask", "escalate"]
    confidence: Literal["high", "medium", "low"]
    response: str = Field(..., description="Draft reply, clarifying question, or escalation summary")
    citations: List[str] = Field(default_factory=list, description="Article IDs used in response")
    missing_info: Optional[str] = None
    escalation_reason: Optional[str] = None
    escalation_summary: Optional[str] = None


# ── Outbound ──────────────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    action: Literal["resolve", "ask", "escalate"]
    response: str
    citations: List[str] = []
    account_id: str
    escalation_summary: Optional[str] = None
    error: Optional[str] = None
