"""
app.py — Entry point. Stage 1 placeholder.
Starts FastAPI, initialises DB.
"""

import uvicorn
from fastapi import FastAPI
from src.config import HOST, PORT
from src.database import init_db

app = FastAPI(title="CSR Assistant", version="0.1.0")


@app.on_event("startup")
async def startup():
    print("[STARTUP] Initialising database...")
    init_db()
    print("[STARTUP] Done.")


@app.get("/health")
def health():
    return {"status": "ok", "stage": 1}


if __name__ == "__main__":
    uvicorn.run("app:app", host=HOST, port=PORT, reload=False)
