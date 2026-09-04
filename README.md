TRACK_ID=PS04

# CSR Assistant — Customer Support Resolution Assistant

An AI-powered support desk assistant for a broadband and mobile provider. It triages incoming customer requests using the conversation history, customer account records, and a knowledge base of support articles — resolving routine cases, asking targeted follow-up questions, or escalating complex cases to human agents with a full context handover.

## What It Does

- **Resolves** routine billing, connection, and plan queries grounded in KB articles (with citations)
- **Asks** for exactly what's missing when information is incomplete — no more, no less
- **Escalates** complex or uncertain cases to a human agent with a concise handover summary (issue, what's established, what's been tried) so the customer never repeats themselves

## How to Run

### 1. Set your Gemini API Key
```bash
# Windows (PowerShell)
$env:GEMINI_API_KEY="your-api-key-here"

# Windows (GitBash / Linux / Mac)
export GEMINI_API_KEY="your-api-key-here"
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the application
```bash
python app.py
```

Visit: [http://localhost:8000](http://localhost:8000)

## Data & Documents

All data is generated and committed to this repository:

- `data/articles/` — 8 support knowledge base articles covering billing, connection, plans, roaming, payments, and account management (markdown format)
- `data/accounts.db` — SQLite database with sample customers, plans, accounts, billing history, and support tickets
- `data/faiss.index` — Pre-built FAISS vector index of KB articles (committed so startup is fast)
- `data/article_metadata.json` — Article ID-to-filepath mapping for retrieval

## Architecture

```
app.py                  ← FastAPI app, serves frontend + API routes
src/
  config.py             ← Constants, environment config
  database.py           ← SQLite account/ticket lookup (deterministic)
  retrieval.py          ← FAISS + Gemini embeddings (deterministic)
  llm.py                ← All Gemini LLM calls (isolated)
  resolver.py           ← Triage logic: resolve / ask / escalate
  models.py             ← Pydantic request/response schemas
data/
  articles/             ← KB markdown articles
  accounts.db           ← Customer records
  faiss.index           ← Pre-built vector index
frontend/dist/          ← Built chat UI (served by FastAPI)
```

## Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Your Google Gemini API key (required) |

## Demo Video

[Watch Demo](#) ← Link will be added before submission
