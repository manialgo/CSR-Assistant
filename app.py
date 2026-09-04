"""
app.py — Main entry point. Starts the entire application on port 8000.

Single command: python app.py
  - Initialises SQLite database
  - Loads FAISS retrieval index
  - Serves FastAPI backend (REST API)
  - Serves frontend (HTML chat UI from frontend/dist/)

All startup must complete within 90 seconds (judge constraint).
"""

import os
import sys
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import HOST, PORT, FRONTEND_DIR, GEMINI_API_KEY
from src.database import init_db
from src.retrieval import load_index
from src.models import ChatRequest, ChatResponse, Message
from src.resolver import resolve


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all resources at startup. Fail loudly if key is missing."""

    # Check API key before anything else
    if not GEMINI_API_KEY:
        print("\n[STARTUP ERROR] GEMINI_API_KEY is not set.")
        print("  Set it with: export GEMINI_API_KEY=your-key-here")
        print("  Then restart the application.\n")
        sys.exit(1)

    print("[STARTUP] Initialising database...")
    init_db()

    print("[STARTUP] Loading retrieval index...")
    load_index()

    print(f"[STARTUP] CSR Assistant ready at http://localhost:{PORT}")
    print("[STARTUP] Press Ctrl+C to stop.\n")

    yield  # App runs here

    print("[SHUTDOWN] CSR Assistant stopped.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CSR Assistant",
    description="Customer Support Resolution Assistant for NexusNow",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check — used by judges to verify app is up within 90s."""
    return {
        "status": "ok",
        "service": "CSR Assistant",
        "version": "1.0.0",
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Accepts a conversation + account_id and returns
    a triage decision: resolve, ask, or escalate.

    Request body:
        account_id : str            — Customer account ID (e.g. "ACC001")
        messages   : List[Message]  — Full conversation history

    Response:
        action            : resolve | ask | escalate
        response          : The draft response text
        citations         : KB article IDs used
        escalation_summary: Handover summary (only when action=escalate)
    """
    if not request.messages:
        raise HTTPException(
            status_code=422,
            detail="messages list cannot be empty."
        )

    try:
        result = resolve(
            account_id=request.account_id,
            messages=request.messages,
        )
        return result
    except Exception as exc:
        # Last-resort catch — should not normally reach here
        # (resolver.py handles all failure modes internally)
        print(f"[API] Unhandled error in /api/chat: {exc}")
        return ChatResponse(
            action="escalate",
            response=(
                "We're experiencing a technical difficulty. "
                "A human agent will be with you shortly."
            ),
            citations=[],
            account_id=request.account_id,
            escalation_summary=(
                f"ISSUE: System error during automated triage.\n"
                f"ESTABLISHED: Account {request.account_id} — last message: "
                f"{request.messages[-1].content[:100] if request.messages else 'N/A'}\n"
                f"TRIED: Automated resolution (failed)\n"
                f"PRIORITY: High"
            ),
            error=str(exc),
        )


@app.get("/api/account/{account_id}")
async def get_account_info(account_id: str):
    """
    Fetch account info for the UI's account lookup panel.
    Returns plan, status, and recent tickets.
    """
    from src.database import get_account
    account = get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found."
        )
    return account


@app.get("/api/accounts")
async def list_demo_accounts():
    """
    Return a list of demo account IDs for the UI's quick-select panel.
    Makes it easy for judges to switch between different scenarios.
    """
    return {
        "accounts": [
            {"id": "ACC001", "name": "Arjun Mehta",    "plan": "Fiber 500",    "status": "active",    "note": "Good standing"},
            {"id": "ACC002", "name": "Priya Sharma",   "plan": "Mobile Plus",  "status": "active",    "note": "Bill due today"},
            {"id": "ACC003", "name": "Rahul Verma",    "plan": "Bundle 500",   "status": "active",    "note": "Recent plan change"},
            {"id": "ACC004", "name": "Sneha Iyer",     "plan": "Fiber 100",    "status": "suspended", "note": "3 months overdue"},
            {"id": "ACC005", "name": "Vikram Nair",    "plan": "Mobile Max",   "status": "active",    "note": "Open roaming ticket"},
            {"id": "ACC006", "name": "Meera Pillai",   "plan": "Fiber 1000",   "status": "active",    "note": "Internet outage open"},
            {"id": "ACC007", "name": "Karthik Rajan",  "plan": "Bundle Max",   "status": "active",    "note": "Slow speed ticket"},
            {"id": "ACC008", "name": "Divya Krishnan", "plan": "Mobile Basic", "status": "active",    "note": "Bill due"},
            {"id": "ACC009", "name": "Aditya Gupta",   "plan": "Fiber 500",    "status": "active",    "note": "Billing dispute open"},
            {"id": "ACC010", "name": "Ananya Reddy",   "plan": "Mobile Plus",  "status": "cancelled", "note": "Recently cancelled"},
        ]
    }


# ── Frontend serving ──────────────────────────────────────────────────────────

FRONTEND_INDEX = FRONTEND_DIR / "index.html"

if FRONTEND_INDEX.exists():
    @app.get("/", response_class=HTMLResponse)
    async def serve_ui():
        """Serve the chat UI."""
        return HTMLResponse(FRONTEND_INDEX.read_text(encoding="utf-8"))

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_ui_paths(full_path: str):
        """Catch-all so SPA routes don't 404."""
        # Don't intercept API routes
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404)
        return HTMLResponse(FRONTEND_INDEX.read_text(encoding="utf-8"))

else:
    @app.get("/", response_class=HTMLResponse)
    async def serve_no_ui():
        return HTMLResponse(
            "<h1>CSR Assistant is running</h1>"
            "<p>POST <code>/api/chat</code> to interact. "
            "GET <code>/health</code> for status.</p>"
        )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
